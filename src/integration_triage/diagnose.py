"""Turn a ticket plus request logs into one diagnosed cause with cited evidence."""

from __future__ import annotations

from .causes import CAUSES, MATCHERS, PRIORITY
from .models import Diagnosis, LogEntry

LOW_CONFIDENCE = 0.65


def _severity(cause_id: str, users: int) -> str:
    if cause_id in ("upstream_outage", "platform_latency"):
        return "sev1" if users >= 3 else "sev2"
    return CAUSES[cause_id].severity


def diagnose(entries: list[LogEntry], ticket: str = "") -> Diagnosis:
    failing = [e for e in entries if e.failed]
    matches = {cid: m for cid, fn in MATCHERS.items() if (m := fn(entries, ticket))}

    if not matches:
        cause_id = "unknown" if failing else "insufficient_data"
        evidence = failing[:10]
        users = len({e.user_id for e in failing if e.user_id})
        first, last = _span(failing or entries)
        return Diagnosis(cause_id, 0.5 if failing else 0.9, tuple(evidence), (), {},
                         _severity(cause_id, users), CAUSES[cause_id].escalate, users,
                         first, last)

    total = len({e.request_id for m in matches.values() for e in m.evidence}) or 1
    scored = sorted(
        ((m.base * (0.5 + 0.5 * len(m.evidence) / total), cid) for cid, m in matches.items()),
        key=lambda s: (-s[0], PRIORITY.index(s[1])),
    )
    score, cause_id = scored[0]
    match = matches[cause_id]
    users = len({e.user_id for e in match.evidence if e.user_id})
    first, last = _span(match.evidence)
    low = score < LOW_CONFIDENCE
    return Diagnosis(
        cause_id=cause_id,
        confidence=round(score, 3),
        evidence=tuple(match.evidence),
        alternatives=tuple((cid, round(s, 3)) for s, cid in scored[1:]),
        detail={**match.detail, "low_confidence": low},
        severity=_severity(cause_id, users),
        escalate=CAUSES[cause_id].escalate or low,
        users_affected=users,
        first_seen=first,
        last_seen=last,
    )


def _span(entries: list[LogEntry]) -> tuple[str, str]:
    stamps = sorted(e.ts for e in entries if e.ts)
    return (stamps[0], stamps[-1]) if stamps else ("", "")
