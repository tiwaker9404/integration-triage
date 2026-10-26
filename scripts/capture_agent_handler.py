#!/usr/bin/env python3
"""Capture real Merge Agent Handler responses as request logs that `triage` can read.

Makes a handful of MCP calls on purpose (some correct, some deliberately wrong), records each
response's status, X-Request-ID, latency and error text, and writes one JSONL file per scenario
to real/. Standard library only. The full API key is never written anywhere; only its first
8 characters are kept, as a dashboard would show.

    export AH_KEY=<test access key>            # Settings > API Keys, a TEST key
    export AH_TOOL_PACK=<tool pack id>         # from the Tool Pack's URL
    export AH_USER=<test registered user id>   # from the Registered Users page
    python scripts/capture_agent_handler.py              # baseline, wrong key, unknown user
    python scripts/capture_agent_handler.py --tool-call some_connector__some_tool

Keep volumes tiny: 3 calls per scenario by default. Do not use a production key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("AH_BASE_URL", "https://ah-api.merge.dev")


def mcp_url(tool_pack: str, user: str) -> str:
    return f"{BASE}/api/v1/tool-packs/{tool_pack}/registered-users/{user}/mcp"


def call(url: str, key: str, payload: dict, session: str | None) -> dict:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "Mcp-Session-Id": session or str(uuid.uuid4())}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers,
                                 method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, hdrs, body = resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, hdrs, body = exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        return {"status": 0, "headers": {}, "body": None, "raw": str(exc.reason),
                "ms": int((time.perf_counter() - started) * 1000)}
    return {"status": status, "headers": {k.lower(): v for k, v in hdrs.items()},
            "body": _parse(body, hdrs), "raw": body[:500],
            "ms": int((time.perf_counter() - started) * 1000)}


def _parse(body: str, headers: dict) -> dict | None:
    """JSON, or the last `data:` event of a server-sent-events stream."""
    ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
    if "event-stream" in ctype:
        events = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]
        body = events[-1] if events else ""
    try:
        return json.loads(body) if body else None
    except json.JSONDecodeError:
        return None


def record(scenario: str, res: dict, key: str, user: str, method: str, tool: str | None) -> dict:
    body = res["body"] if isinstance(res["body"], dict) else {}
    err = body.get("error") if isinstance(body.get("error"), (dict, str)) else None
    meta = (body.get("result") or {}).get("_meta", {}) if isinstance(body.get("result"), dict) else {}
    err_data = err.get("data") if isinstance(err, dict) and isinstance(err.get("data"), dict) else {}
    rid = (res["headers"].get("x-request-id") or meta.get("dev.merge/request_id")
           or err_data.get("dev.merge/request_id") or f"{scenario}-{uuid.uuid4().hex[:8]}")
    if isinstance(err, dict):
        code, message = err.get("code"), err.get("message", "")
    else:
        code = body.get("code") or body.get("error_code")
        message = err or body.get("detail") or body.get("message") or ""
        if not message and res["status"] >= 400:
            message = (res["raw"] or "")[:300]
    return {
        "request_id": rid, "status": res["status"],
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "POST", "path": "/mcp", "latency_ms": res["ms"], "user_id": user,
        "key_prefix": key[:8], "tool": tool, "error_code": None if code is None else str(code),
        "message": str(message)[:300], "jsonrpc_error": isinstance(err, dict),
        "rpc_method": method, "scenario": scenario,
    }


def run(scenario: str, url: str, key: str, user: str, n: int, tool: str | None) -> list[dict]:
    rows = []
    for _ in range(n):
        init = call(url, key, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                          "clientInfo": {"name": "triage-capture", "version": "1"}}},
                    None)
        rows.append(record(scenario, init, key, user, "initialize", None))
        if init["status"] != 200:
            continue
        session = init["headers"].get("mcp-session-id")
        if tool:
            res = call(url, key, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": tool, "arguments": {}}}, session)
            rows.append(record(scenario, res, key, user, "tools/call", tool))
        else:
            res = call(url, key, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session)
            rows.append(record(scenario, res, key, user, "tools/list", None))
        time.sleep(0.5)  # be gentle
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", default="real", help="directory for the JSONL files")
    p.add_argument("-n", type=int, default=3, help="calls per scenario (keep it small)")
    p.add_argument("--tool-call", metavar="NAME",
                   help="also call this tool name (use one NOT in your pack to see that error)")
    args = p.parse_args()
    try:
        key, pack, user = os.environ["AH_KEY"], os.environ["AH_TOOL_PACK"], os.environ["AH_USER"]
    except KeyError as exc:
        print(f"set {exc.args[0]} first (see the top of this file)", file=sys.stderr)
        return 2

    scenarios = {
        "baseline": (mcp_url(pack, user), key, user, None),
        "wrong_key": (mcp_url(pack, user), key[:-6] + "XXXXXX", user, None),
        "unknown_user": (mcp_url(pack, "00000000-0000-4000-8000-000000000000"), key,
                         "00000000-0000-4000-8000-000000000000", None),
    }
    if args.tool_call:
        scenarios["tool_call"] = (mcp_url(pack, user), key, user, args.tool_call)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"{'scenario':<13} {'rpc':<11} {'status':>6}  request_id / message")
    for name, (url, k, u, tool) in scenarios.items():
        rows = run(name, url, k, u, args.n, tool)
        (out / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        for r in rows:
            note = f"jsonrpc error {r['error_code']}: " if r["jsonrpc_error"] else ""
            print(f"{name:<13} {r['rpc_method']:<11} {r['status']:>6}  {r['request_id']}  "
                  f"{note}{r['message'][:70]}")
    print(f"\nwrote {', '.join(str(out / f'{n}.jsonl') for n in scenarios)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
