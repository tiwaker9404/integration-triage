"""Service settings from environment variables, validated at startup."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int, low: int = 1) -> int:
    raw = os.environ.get(name, "")
    try:
        value = int(raw) if raw else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < low:
        raise ValueError(f"{name} must be >= {low}, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    env: str = "dev"                      # dev | prod
    api_keys: tuple[str, ...] = ()
    db_path: str = "data/triage.db"
    max_body_mb: int = 20
    max_entries: int = 100_000
    rate_limit_per_min: int = 120
    docs_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get("TRIAGE_ENV", "dev").lower()
        if env not in ("dev", "prod"):
            raise ValueError(f"TRIAGE_ENV must be dev or prod, got {env!r}")
        keys = tuple(k.strip() for k in os.environ.get("TRIAGE_API_KEYS", "").split(",") if k.strip())
        s = cls(env=env, api_keys=keys,
                db_path=os.environ.get("TRIAGE_DB_PATH", "data/triage.db"),
                max_body_mb=_int("TRIAGE_MAX_BODY_MB", 20),
                max_entries=_int("TRIAGE_MAX_ENTRIES", 100_000),
                rate_limit_per_min=_int("TRIAGE_RATE_LIMIT_PER_MIN", 120),
                docs_enabled=os.environ.get("TRIAGE_DOCS", "1" if env == "dev" else "0") == "1")
        s.validate()
        return s

    def validate(self) -> None:
        if self.env == "prod":
            if not self.api_keys:
                raise ValueError("TRIAGE_ENV=prod requires TRIAGE_API_KEYS (comma-separated)")
            if any(len(k) < 16 for k in self.api_keys):
                raise ValueError("every key in TRIAGE_API_KEYS must be at least 16 characters")

    @property
    def auth_required(self) -> bool:
        return self.env == "prod" or bool(self.api_keys)
