"""Write the three things a support engineer produces for every incident.

  customer_reply     what to send the customer
  escalation_packet  what to hand an engineer so they never have to ask a follow-up
  runbook_entry      what the next person on the team should do when it happens again

Everything passes through `redact` on the way out.
"""

from __future__ import annotations

from statistics import median

from .causes import CAUSES
from .models import Diagnosis, LogEntry
from .redact import redact


def _short(ts: str) -> str:
    return ts.replace("T", " ").replace("Z", "") if ts else "unknown time"


def _ids(entries: tuple[LogEntry, ...], k: int = 3) -> str:
    return ", ".join(e.request_id for e in entries[:k]) or "n/a"


def _fields(d: Diagnosis) -> dict:
    ev = d.evidence
    users = len({e.user_id for e in ev if e.user_id})
    connectors = sorted({e.connector for e in ev if e.connector})
    rotated = d.detail.get("rotated")
    return {
        "n": len(ev), "first": _short(d.first_seen), "last": _short(d.last_seen),
        "ids": _ids(ev), "users": users or d.users_affected,
        "retry": d.detail.get("retry", 0), "prefix": d.detail.get("prefix", "(unknown)"),
        "median_ms": d.detail.get("median_ms", int(median([e.latency_ms for e in ev]) if ev else 0)),
        "path": d.detail.get("path", ""), "cursor": d.detail.get("cursor", ""),
        "connectors": ", ".join(connectors) or "the connected app",
        "rotation_note": (
            "A different key succeeded in the same window, which usually means the old key "
            "was rotated, and rotating a production key invalidates the old one immediately."
            if rotated else
            "The key was not recognised, which usually means a copy error, the wrong "
            "environment, or a key that was deleted."),
    }


def _keep(d: Diagnosis) -> list[str]:
    """IDs the text cites as evidence; long random-looking ones must not be redacted."""
    return [e.request_id for e in d.evidence] + [e.user_id for e in d.evidence if e.user_id]


def customer_reply(d: Diagnosis) -> str:
    cause = CAUSES[d.cause_id]
    finding = cause.finding.format(**_fields(d))
    steps = " ".join(f"{i}) {s}" for i, s in enumerate(cause.steps, 1))
    if d.cause_id == "insufficient_data":
        closing = "Once I have those, I will dig in right away."
    elif d.escalate:
        closing = ("I have passed this to our engineering team with the request IDs above and "
                   "will update you as soon as I hear back.")
    else:
        closing = "Reply here with how it goes and I will help from there."
    body = (f"Thanks for the detail, and sorry for the disruption.\n\n"
            f"What I found: {finding}\n\nWhat to do: {steps}\n\n{closing}")
    return redact(body, keep=_keep(d))


def escalation_packet(d: Diagnosis, ticket: str = "") -> str:
    cause = CAUSES[d.cause_id]
    rows = "\n".join(
        f"| {e.request_id} | {_short(e.ts)} | {e.status} | {e.path or e.tool or '-'} | "
        f"{e.latency_ms} | {e.user_id or '-'} |" for e in d.evidence[:10])
    alts = ", ".join(f"{cid} ({s:.2f})" for cid, s in d.alternatives) or "none matched"
    page = "YES" if d.page_oncall else "no"
    repro = ("curl -i -X POST \"$BASE_URL/<path>\" -H \"Authorization: Bearer $API_KEY\" "
             "# use a test key; substitute a failing path and user ID from the table")
    told = " ".join(f"{i}) {s}" for i, s in enumerate(cause.steps, 1))
    if d.detail.get("low_confidence"):
        ask = "Low-confidence match: please confirm or correct the diagnosis."
    elif cause.escalate:
        ask = (f"Please confirm the diagnosis and tell me what to say to the customer. "
               f"Why this needs an engineer: {cause.escalate_when}")
    else:
        ask = (f"Review only; this is normally handled by support. Escalate if: "
               f"{cause.escalate_when}")
    packet = f"""# Escalation: {cause.title}

**Severity:** {d.severity}  |  **Page on-call:** {page}  |  **Confidence:** {d.confidence:.2f}
**Window:** {_short(d.first_seen)} to {_short(d.last_seen)} UTC  |  **Failing calls:** {len(d.evidence)}  |  **Users affected:** {d.users_affected}

## Customer report
{ticket.strip() or "(no ticket text supplied)"}

## Evidence
| request_id | time (UTC) | status | path / tool | latency ms | user |
|---|---|---|---|---|---|
{rows or "| - | - | - | - | - | - |"}

## Suspected cause
{cause.title}. How it was confirmed: {cause.confirm}

## Other candidates considered
{alts}

## Already told the customer
{told}

## Repro
`{repro}`

## What I need from engineering
{ask}
"""
    return redact(packet, keep=_keep(d))


def runbook_entry(cause_id: str) -> str:
    c = CAUSES[cause_id]
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(c.steps, 1))
    macro = c.finding.replace("{", "<").replace("}", ">")
    return redact(f"""# {c.title}

`{c.id}`  |  default severity: {c.severity}  |  needs an engineer: {"yes" if c.escalate else "no"}  |  basis: {c.source}

## How to confirm
{c.confirm}

## What to tell the customer
{steps}

## Reply macro (fill the <placeholders> from the log evidence)
> {macro}

## Escalate when
{c.escalate_when}
""")
