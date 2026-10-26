"""Quality checks for outgoing replies. Used by the CLI, the MCP tools and the eval suite."""

from __future__ import annotations

import re

from .models import Diagnosis
from .redact import leaked

MAX_WORDS = 190
_PROMISES = ("guarantee", "100%", "definitely will", "will be fixed today", "no exceptions")
_BLAME = ("your fault", "you should have", "you failed", "user error", "obviously")
_STEP_RE = re.compile(r"\b1\)")


def reply_problems(reply: str, d: Diagnosis, secrets: list[str] | None = None) -> list[str]:
    low = reply.lower()
    problems: list[str] = []
    problems += [f"leaks secret {s[:6]}..." for s in leaked(reply, secrets or [])]
    problems += [f"overpromises: {p!r}" for p in _PROMISES if p in low]
    problems += [f"blames the customer: {p!r}" for p in _BLAME if p in low]
    if len(reply.split()) > MAX_WORDS:
        problems.append(f"too long (>{MAX_WORDS} words)")
    if not _STEP_RE.search(reply):
        problems.append("no concrete next step")
    cited = [e.request_id for e in d.evidence[:3]]
    if cited and not any(rid in reply for rid in cited):
        problems.append("cites no request ID")
    return problems
