"""The Agent Handler capture script and MCP (JSON-RPC) error handling, without network."""

import importlib.util
import json
from pathlib import Path

from integration_triage.diagnose import diagnose
from integration_triage.logs import load_logs, parse_entry

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_agent_handler.py"
spec = importlib.util.spec_from_file_location("capture", SCRIPT)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

KEY = "ah_test_SECRETSECRETSECRET123"


def res(status, body, headers=None):
    return {"status": status, "headers": headers or {}, "body": body,
            "raw": json.dumps(body), "ms": 42}


def test_records_never_contain_the_full_key():
    r = capture.record("wrong_key", res(401, {"detail": "Invalid API key."},
                                        {"x-request-id": "rq_1"}), KEY, "u1", "initialize", None)
    assert r["request_id"] == "rq_1" and r["status"] == 401 and r["key_prefix"] == KEY[:8]
    assert KEY not in json.dumps(r) and r["message"] == "Invalid API key."


def test_jsonrpc_errors_and_request_ids_from_meta_are_captured():
    body = {"jsonrpc": "2.0", "id": 2, "error": {"code": -32602, "message": "Unknown tool",
                                                 "data": {"dev.merge/request_id": "rq_meta"}}}
    r = capture.record("tool_call", res(200, body), KEY, "u1", "tools/call", "x__y")
    assert r["jsonrpc_error"] and r["error_code"] == "-32602" and r["request_id"] == "rq_meta"


def test_server_sent_events_are_parsed():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n'
    assert capture._parse(body, {"Content-Type": "text/event-stream"}) == \
        {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_mcp_url_format_matches_the_docs():
    assert capture.mcp_url("P", "U").endswith("/api/v1/tool-packs/P/registered-users/U/mcp")


def test_jsonrpc_error_inside_http_200_is_a_failure():
    e = parse_entry({"request_id": "a", "status": 200, "error_code": "-32602"})
    assert e.rpc_error and e.failed
    assert not parse_entry({"request_id": "b", "status": 200}).failed


def test_tool_outside_scope_is_diagnosed_not_ignored():
    rows = [{"request_id": f"r{i}", "status": 200, "jsonrpc_error": True, "error_code": "-32602",
             "message": "Unknown tool", "tool": "notion__search"} for i in range(2)]
    d = diagnose(load_logs("\n".join(json.dumps(r) for r in rows)).entries)
    assert d.cause_id == "tool_not_in_scope" and not d.escalate
