"""Strip secrets and personal data before anything leaves the tool.

Customers paste API keys into tickets, and platforms echo key fragments in error messages, so
every customer reply, escalation packet and runbook passes through `redact`.

Two layers:
  1. Known shapes: common vendor key prefixes, bearer tokens, JWTs, `key=value` secrets, private
     key blocks, emails, Luhn-valid card numbers, phone numbers.
  2. Unknown shapes: any long token that mixes letters and digits and looks random (high
     Shannon entropy) is treated as a secret. This is what catches a key format nobody listed.

Identifiers the reply must keep (request IDs cited as evidence, UUIDs) are passed in `keep`
or recognised as UUIDs, and are never redacted.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

_KNOWN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b(?:sk|rk|pk|whsec)_(?:live_|test_)?[A-Za-z0-9]{6,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\blsv2_[a-z]{2}_[A-Za-z0-9_]{20,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\b"),
     "[REDACTED_JWT]"),
    (re.compile(r"(?i)\b(Bearer|Basic|Token)\s+(?!\[REDACTED)[A-Za-z0-9._~+/=\-]{8,}"),
     r"\1 [REDACTED_TOKEN]"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token|refresh[_-]?token|"
                r"client[_-]?secret|auth[_-]?token|x-api-key)(\"?\s*[:=]\s*\"?)(?!\[REDACTED)"
                r"[^\s,;\"'&]{6,}"), r"\1\2[REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
)
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_PHONE = re.compile(r"(?<![\w#])(?:\+?\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}\b")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_TOKEN = re.compile(r"(?<![\w\-])[A-Za-z0-9][A-Za-z0-9_\-]{23,}(?![\w\-])")

ENTROPY_THRESHOLD = 3.6  # bits per character; English words and IDs sit well below this


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def entropy(s: str) -> float:
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def looks_secret(token: str) -> bool:
    """A long token mixing letters and digits with near-random characters."""
    if _UUID.match(token):
        return False
    letters = sum(ch.isalpha() for ch in token)
    digits = sum(ch.isdigit() for ch in token)
    return letters >= 4 and digits >= 3 and entropy(token) >= ENTROPY_THRESHOLD


def redact(text: str, keep: Iterable[str] = ()) -> str:
    keep_set = {k for k in keep if k}
    protected: dict[str, str] = {}
    for i, k in enumerate(sorted(keep_set, key=len, reverse=True)):  # shield kept IDs first
        marker = f"\x00KEEP{i}\x00"
        if k in text:
            text = text.replace(k, marker)
            protected[marker] = k
    for pattern, repl in _KNOWN:
        text = pattern.sub(repl, text)
    text = _CARD.sub(lambda m: "[REDACTED_CARD]" if _luhn(re.sub(r"\D", "", m.group(0)))
                     else m.group(0), text)
    text = _PHONE.sub("[REDACTED_PHONE]", text)
    text = _TOKEN.sub(lambda m: "[REDACTED_TOKEN]" if looks_secret(m.group(0)) else m.group(0),
                      text)
    for marker, original in protected.items():
        text = text.replace(marker, original)
    return text


def leaked(text: str, secrets: list[str]) -> list[str]:
    """Which of the known secret strings still appear in `text`."""
    return [s for s in secrets if s and s in text]
