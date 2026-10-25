import asyncio
import json
import sys

import pytest

from integration_triage import mcp_server
from integration_triage.evaluate import load_cases

CASE = next(c for c in load_cases() if c["id"] == "case10")
LOGS = "\n".join(json.dumps(r) for r in CASE["logs"])


def test_tool_functions_return_redacted_structured_output():
    out = mcp_server.diagnose_incident(LOGS, CASE["ticket"])
    assert out["cause"] == "invalid_api_key" and out["reply_problems"] == []
    assert CASE["gold"]["secrets"][0] not in json.dumps(out)


def test_escalations_include_the_packet():
    case = next(c for c in load_cases() if c["id"] == "case19")
    out = mcp_server.diagnose_incident("\n".join(json.dumps(r) for r in case["logs"]), "down")
    assert out["page_oncall"] and "# Escalation" in out["escalation_packet"]


def test_get_runbook_rejects_unknown_causes():
    assert mcp_server.get_runbook("rate_limited").startswith("# ")
    with pytest.raises(ValueError):
        mcp_server.get_runbook("nope")
    assert len(mcp_server.list_causes()) >= 10


def test_server_works_over_real_stdio():
    pytest.importorskip("mcp.client")
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    async def go():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "integration_triage.mcp_server"])
        async with Client(params) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            res = await client.call_tool("diagnose_incident",
                                         {"logs_jsonl": LOGS, "ticket": CASE["ticket"]})
            return names, res

    names, res = asyncio.run(asyncio.wait_for(go(), timeout=60))
    assert names == {"diagnose_incident", "get_runbook", "list_causes"}
    assert not res.is_error and res.structured_content["cause"] == "invalid_api_key"
