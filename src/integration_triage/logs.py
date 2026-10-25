from __future__ import annotations

import json
from typing import Any

from .models import LogEntry


def parse_entry(raw: dict[str, Any]) -> LogEntry:
    """Build a LogEntry from a loosely-shaped dict. Only `request_id` and `status` are required."""
    if "request_id" not in raw or "status" not in raw:
        raise ValueError("each log line needs at least 'request_id' and 'status'")
    err = raw.get("error") or {}
    headers = {str(k).lower(): v for k, v in (raw.get("headers") or {}).items()}
    retry = raw.get("retry_after", headers.get("retry-after"))
    return LogEntry(
        request_id=str(raw["request_id"]),
        status=int(raw["status"]),
        ts=str(raw.get("ts", "")),
        method=str(raw.get("method", "POST")),
        path=str(raw.get("path", "")),
        latency_ms=int(raw.get("latency_ms", 0) or 0),
        user_id=raw.get("user_id"),
        connector=raw.get("connector"),
        tool=raw.get("tool"),
        key_prefix=raw.get("key_prefix"),
        error_code=raw.get("error_code") or err.get("code"),
        message=str(raw.get("message") or err.get("message") or ""),
        retry_after=int(retry) if retry not in (None, "") else None,
        upstream_status=raw.get("upstream_status"),
        cursor=raw.get("cursor"),
        source=str(raw.get("source", "api")),
        breakdown={k: int(v) for k, v in (raw.get("breakdown") or {}).items()},
    )


def parse_jsonl(text: str) -> list[LogEntry]:
    """Parse JSON-lines logs, returned in timestamp order (stable for equal timestamps)."""
    entries: list[LogEntry] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(parse_entry(json.loads(line)))
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ValueError(f"line {lineno}: {exc}") from exc
    return sorted(entries, key=lambda e: e.ts)
