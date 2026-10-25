from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LogEntry:
    """One request or tool call, as it would appear in a platform's request log."""

    request_id: str
    status: int
    ts: str = ""
    method: str = "POST"
    path: str = ""
    latency_ms: int = 0
    user_id: str | None = None
    connector: str | None = None
    tool: str | None = None
    key_prefix: str | None = None  # the non-secret prefix a dashboard shows, e.g. "sk_live_ab12"
    error_code: str | None = None
    message: str = ""
    retry_after: int | None = None
    upstream_status: int | None = None  # status the third-party API returned, if any
    cursor: str | None = None
    source: str = "api"  # "api" or "webhook"
    breakdown: dict[str, int] = field(default_factory=dict)  # auth/scan/dispatch/third_party ms

    @property
    def overhead_ms(self) -> int | None:
        """Time spent outside the third-party call, when a breakdown is available."""
        if "third_party" not in self.breakdown:
            return None
        return max(0, self.latency_ms - self.breakdown["third_party"])

    @property
    def failed(self) -> bool:
        return self.status >= 400


@dataclass(frozen=True)
class Diagnosis:
    cause_id: str
    confidence: float
    evidence: tuple[LogEntry, ...]
    alternatives: tuple[tuple[str, float], ...]
    detail: dict
    severity: str  # sev1 (page on-call) .. sev3 (single user)
    escalate: bool
    users_affected: int
    first_seen: str
    last_seen: str

    @property
    def page_oncall(self) -> bool:
        return self.severity == "sev1"
