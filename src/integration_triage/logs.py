"""Read request logs in the shapes real platforms export them.

Accepted inputs:
  * JSON lines, a JSON array, or a JSON object wrapping a list (`data`, `logs`, `items`, ...)
  * CSV with a header row
Field names vary between platforms, so each field is looked up through a list of common aliases
(`status`, `status_code`, `response.status`, ...), and a mapping file can name any other path:

    {"request_id": "meta.trace", "status": "http.code", "ts": "started"}

Timestamps are normalised to UTC ISO-8601 (`2026-10-20T14:03:11Z`) from ISO strings with any
offset, naive `YYYY-MM-DD HH:MM:SS` (assumed UTC), or epoch seconds/milliseconds, so entries from
mixed sources sort correctly.

`load_logs` is lenient: bad lines are skipped and reported. `parse_jsonl` is strict and raises on
the first bad line (useful in tests and pipelines that must not lose data silently).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import LogEntry

MAX_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 100_000

ALIASES: dict[str, tuple[str, ...]] = {
    "request_id": ("request_id", "requestId", "req_id", "tool_call_id", "toolCallId", "call_id",
                   "trace_id", "traceId", "id", "headers.x-request-id"),
    "status": ("status", "status_code", "statusCode", "http_status", "httpStatus",
               "response.status", "response.status_code", "response.statusCode", "code"),
    "ts": ("ts", "timestamp", "time", "@timestamp", "created_at", "createdAt", "start_time",
           "startTime", "date"),
    "method": ("method", "http_method", "request.method"),
    "path": ("path", "url", "endpoint", "route", "request.path", "request.url"),
    "latency_ms": ("latency_ms", "latencyMs", "duration_ms", "durationMs", "elapsed_ms",
                   "latency", "duration"),
    "user_id": ("user_id", "userId", "registered_user_id", "registeredUserId", "end_user_id",
                "endUserId", "linked_account_id", "account_id", "customer_id"),
    "connector": ("connector", "integration", "app", "provider", "connector_slug"),
    "tool": ("tool", "tool_name", "toolName", "action"),
    "key_prefix": ("key_prefix", "keyPrefix", "api_key_prefix", "key_id"),
    "error_code": ("error_code", "errorCode", "error.code", "error.type", "response.error.code"),
    "message": ("message", "error.message", "error_message", "errorMessage", "response.error.message",
                "detail", "error.detail", "response.body.error", "msg"),
    "retry_after": ("retry_after", "retryAfter", "headers.retry-after"),
    "upstream_status": ("upstream_status", "upstreamStatus", "third_party_status",
                        "remote_status", "provider_status"),
    "cursor": ("cursor", "page_cursor", "next_cursor_sent", "query.cursor"),
    "source": ("source", "kind", "type"),
    "breakdown": ("breakdown", "latency_breakdown", "timings"),
    "rpc_error": ("jsonrpc_error", "rpc_error", "is_rpc_error"),
}
_LIST_KEYS = ("data", "logs", "items", "results", "records", "runs", "entries", "events")


@dataclass
class ParseReport:
    entries: list[LogEntry]
    format: str
    total: int = 0
    skipped: list[str] = field(default_factory=list)
    unparsed_timestamps: int = 0

    @property
    def warnings(self) -> list[str]:
        out = []
        if self.skipped:
            out.append(f"skipped {len(self.skipped)} of {self.total} records: "
                       + "; ".join(self.skipped[:3]) + (" ..." if len(self.skipped) > 3 else ""))
        if self.unparsed_timestamps:
            out.append(f"{self.unparsed_timestamps} timestamps were not recognised, so ordering "
                       "may be off")
        return out


# ------------------------------------------------------------------ helpers
def _get(raw: dict[str, Any], path: str, cache: dict[int, dict[str, Any]] | None = None) -> Any:
    """Dotted lookup, case-insensitive per segment ("headers.Retry-After" works). `cache` holds
    lower-cased copies of the dicts already seen for this record, so the many alias lookups
    per record stay cheap."""
    cur: Any = raw
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        if part in cur:
            cur = cur[part]
            continue
        low = cache.get(id(cur)) if cache is not None else None
        if low is None:
            low = {str(k).lower(): v for k, v in cur.items()}
            if cache is not None:
                cache[id(cur)] = low
        cur = low.get(part.lower())
        if cur is None:
            return None
    return cur


def _first(raw: dict[str, Any], name: str, mapping: dict[str, str] | None,
           cache: dict[int, dict[str, Any]] | None = None) -> Any:
    if mapping and name in mapping:
        return _get(raw, mapping[name], cache)
    for path in ALIASES[name]:
        value = _get(raw, path, cache)
        if value not in (None, ""):
            return value
    return None


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip().removesuffix("ms").strip()))
    except ValueError:
        return None


def normalize_ts(value: Any) -> tuple[str, bool]:
    """Return (UTC ISO string, recognised?). Unrecognised values are returned unchanged."""
    if value in (None, ""):
        return "", True
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().replace(".", "", 1).isdigit()):
        n = float(value)
        if n > 1e11:          # milliseconds
            n /= 1000
        try:
            return datetime.fromtimestamp(n, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), True
        except (OverflowError, OSError, ValueError):
            return str(value), False
    text = str(value).strip()
    candidate = text.replace("Z", "+00:00").replace(" ", "T", 1) if "T" not in text else text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return text, False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), True


# ------------------------------------------------------------------ parsing
def parse_entry(raw: dict[str, Any], mapping: dict[str, str] | None = None,
                fallback_id: str | None = None) -> LogEntry:
    """Build a LogEntry from one record. Needs a status; a request id is synthesised if absent
    and `fallback_id` is given."""
    if not isinstance(raw, dict):
        raise ValueError("record is not an object")
    cache: dict[int, dict[str, Any]] = {}

    def f(name: str) -> Any:
        return _first(raw, name, mapping, cache)

    status = _int(f("status"))
    if status is None or not 100 <= status <= 599:
        raise ValueError("missing or invalid HTTP status")
    rid = f("request_id")
    if rid in (None, ""):
        if fallback_id is None:
            raise ValueError("each log line needs at least 'request_id' and 'status'")
        rid = fallback_id
    err = raw.get("error")
    message = f("message")
    if message is None and isinstance(err, str):
        message = err
    ts, _ = normalize_ts(f("ts"))
    breakdown = f("breakdown")
    source = str(f("source") or "api").lower()
    error_code = _str_or_none(f("error_code"))
    rpc_flag = f("rpc_error")
    rpc_error = (str(rpc_flag).lower() in ("true", "1", "yes") if rpc_flag is not None
                 else bool(error_code and error_code.startswith("-32")))
    return LogEntry(
        request_id=str(rid),
        status=status,
        ts=ts,
        method=str(f("method") or "POST").upper(),
        path=str(f("path") or ""),
        latency_ms=_int(f("latency_ms")) or 0,
        user_id=_str_or_none(f("user_id")),
        connector=_str_or_none(f("connector")),
        tool=_str_or_none(f("tool")),
        key_prefix=_str_or_none(f("key_prefix")),
        error_code=error_code,
        message=str(message or ""),
        retry_after=_int(f("retry_after")),
        upstream_status=_int(f("upstream_status")),
        cursor=_str_or_none(f("cursor")),
        source="webhook" if "webhook" in source else "api",
        breakdown={k: v for k, v in ((k, _int(v)) for k, v in (breakdown or {}).items())
                   if v is not None} if isinstance(breakdown, dict) else {},
        rpc_error=rpc_error,
    )


def _str_or_none(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _records(text: str) -> tuple[str, list[Any], list[str]]:
    """Split raw text into records. Returns (format, records, per-line errors)."""
    stripped = text.lstrip()
    if not stripped:
        return "empty", [], []
    if stripped[0] in "[{":
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            return "json-array", data, []
        if isinstance(data, dict):
            for key in _LIST_KEYS:
                if isinstance(data.get(key), list):
                    return "json-object", data[key], []
            return "jsonl", [data], []
        records, errors = [], []
        for lineno, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                records.append(None)
                errors.append(f"line {lineno}: invalid JSON ({exc.msg})")
        return "jsonl", records, errors
    first = stripped.splitlines()[0]
    if "," in first:
        return "csv", list(csv.DictReader(io.StringIO(stripped))), []
    raise ValueError("unrecognised log format: expected JSON lines, a JSON array or CSV")


def load_logs(text: str, mapping: dict[str, str] | None = None, *,
              max_bytes: int = MAX_BYTES, max_entries: int = MAX_ENTRIES) -> ParseReport:
    """Lenient loader for real exports: skips bad records and reports them."""
    if len(text.encode("utf-8")) > max_bytes:
        raise ValueError(f"logs larger than {max_bytes // (1024 * 1024)} MB; filter to the "
                         "incident window first")
    fmt, records, errors = _records(text)
    if len(records) > max_entries:
        raise ValueError(f"{len(records)} records is over the {max_entries} limit; filter to "
                         "the incident window first")
    report = ParseReport(entries=[], format=fmt, total=len(records), skipped=list(errors))
    for i, raw in enumerate(records, 1):
        if raw is None:
            continue
        try:
            entry = parse_entry(raw, mapping, fallback_id=f"record-{i}")
        except (ValueError, TypeError) as exc:
            report.skipped.append(f"record {i}: {exc}")
            continue
        if entry.ts and not entry.ts.endswith("Z"):
            report.unparsed_timestamps += 1
        report.entries.append(entry)
    report.entries.sort(key=lambda e: e.ts)
    return report


def parse_jsonl(text: str, mapping: dict[str, str] | None = None) -> list[LogEntry]:
    """Strict: raise on the first bad line. Returned in timestamp order."""
    entries: list[LogEntry] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(parse_entry(json.loads(line), mapping))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ValueError(f"line {lineno}: {exc}") from exc
    return sorted(entries, key=lambda e: e.ts)


def load_mapping(text: str) -> dict[str, str]:
    data = json.loads(text)
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise ValueError("mapping must be a JSON object of field -> dotted path")
    unknown = set(data) - set(ALIASES)
    if unknown:
        raise ValueError(f"unknown fields in mapping: {', '.join(sorted(unknown))}; "
                         f"known: {', '.join(ALIASES)}")
    return data
