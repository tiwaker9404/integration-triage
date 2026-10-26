"""The same toolkit as an MCP server, so an agent can triage a ticket itself.

    triage-mcp            # stdio transport; point an MCP client at this command

Tools:
    diagnose_incident(logs_jsonl, ticket)   diagnosis + customer reply (+ escalation packet)
    get_runbook(cause_id)                   the runbook entry for a known cause
    list_causes()                           the catalog, with how each cause was sourced
"""

from __future__ import annotations

from typing import Any

from .causes import CAUSES
from .checks import reply_problems
from .compose import customer_reply, escalation_packet, runbook_entry
from .diagnose import diagnose
from .logs import load_logs

INSTRUCTIONS = (
    "Support-engineering triage tools. Pass request logs as JSON lines (each needs request_id "
    "and status) plus the customer's message. Outputs are already redacted. Always read the "
    "'escalate' and 'page_oncall' fields before telling a customer the issue is resolved."
)


def diagnose_incident(logs_jsonl: str, ticket: str = "") -> dict[str, Any]:
    """Diagnose a failing integration from request logs (JSON lines, JSON array or CSV) and the
    customer's message."""
    report = load_logs(logs_jsonl)
    d = diagnose(report.entries, ticket)
    reply = customer_reply(d)
    out: dict[str, Any] = {
        "cause": d.cause_id,
        "title": CAUSES[d.cause_id].title,
        "confidence": d.confidence,
        "severity": d.severity,
        "escalate": d.escalate,
        "page_oncall": d.page_oncall,
        "users_affected": d.users_affected,
        "evidence_request_ids": [e.request_id for e in d.evidence[:10]],
        "customer_reply": reply,
        "reply_problems": reply_problems(reply, d),
        "parse_warnings": report.warnings,
    }
    if d.escalate:
        out["escalation_packet"] = escalation_packet(d, ticket)
    return out


def get_runbook(cause_id: str) -> str:
    """Return the runbook entry for a cause id (see list_causes)."""
    if cause_id not in CAUSES:
        raise ValueError(f"unknown cause {cause_id!r}; try one of: {', '.join(CAUSES)}")
    return runbook_entry(cause_id)


def list_causes() -> list[dict[str, str]]:
    """List every known cause with its default severity and where its behaviour comes from."""
    return [{"id": c.id, "title": c.title, "severity": c.severity, "source": c.source}
            for c in CAUSES.values()]


def build_server():
    from mcp.server.mcpserver import MCPServer  # mcp>=2

    server = MCPServer("integration-triage", instructions=INSTRUCTIONS)
    for fn in (diagnose_incident, get_runbook, list_causes):
        server.tool()(fn)
    return server


def main() -> None:  # pragma: no cover - exercised by the stdio smoke test
    build_server().run()


if __name__ == "__main__":
    main()
