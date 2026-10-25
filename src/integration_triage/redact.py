"""Strip secrets before anything leaves the tool.

Customers paste API keys into tickets and platforms echo key fragments in error messages, so
every customer reply, escalation packet and runbook passes through `redact`.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:sk|rk|pk|whsec)_(?:live_|test_)?[A-Za-z0-9]{6,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\b"),
     "[REDACTED_JWT]"),
    (re.compile(r"(?i)\bBearer\s+(?!\[REDACTED)[A-Za-z0-9._\-]{8,}"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|access[_-]?token|refresh[_-]?token)"
                r"(\s*[:=]\s*)(?!\[REDACTED)[^\s,;\"']{6,}"), r"\1\2[REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
)


def redact(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def leaked(text: str, secrets: list[str]) -> list[str]:
    """Which of the known secret strings still appear in `text`."""
    return [s for s in secrets if s and s in text]
