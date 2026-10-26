"""Everything between an HTTP request and the diagnosis engine."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any

from .causes import CAUSES
from .checks import reply_problems
from .compose import customer_reply, escalation_packet
from .config import Settings
from .diagnose import diagnose
from .logs import load_logs
from .redact import redact
from .store import Store, now

log = logging.getLogger("integration_triage")


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class TriageService:
    def __init__(self, settings: Settings, store: Store | None = None) -> None:
        self.settings = settings
        self.store = store or Store(settings.db_path)

    def diagnose(self, ticket: str, logs: str, mapping: dict[str, str] | None = None,
                 incident_id: str | None = None) -> dict[str, Any]:
        incident_id = incident_id or f"inc_{uuid.uuid4().hex[:16]}"
        digest = hashlib.sha256(json.dumps([ticket, logs, mapping], sort_keys=True)
                                .encode()).hexdigest()
        existing = self.store.get(incident_id)
        if existing is not None:
            if existing["input_hash"] != digest:
                raise Conflict(incident_id)
            return {**existing["result"], "replayed": True}

        started = time.perf_counter()
        report = load_logs(logs, mapping, max_bytes=self.settings.max_body_mb * 1024 * 1024,
                           max_entries=self.settings.max_entries)
        d = diagnose(report.entries, ticket)
        reply = customer_reply(d)
        result = {
            "incident_id": incident_id,
            "created_at": now(),
            "cause": d.cause_id,
            "title": CAUSES[d.cause_id].title,
            "confidence": d.confidence,
            "severity": d.severity,
            "escalate": d.escalate,
            "page_oncall": d.page_oncall,
            "users_affected": d.users_affected,
            "first_seen": d.first_seen,
            "last_seen": d.last_seen,
            "evidence_request_ids": [e.request_id for e in d.evidence[:20]],
            "alternatives": [{"cause": c, "score": s} for c, s in d.alternatives],
            "reply": reply,
            "reply_problems": reply_problems(reply, d),
            "escalation_packet": escalation_packet(d, ticket) if d.escalate else "",
            "ticket": redact(ticket),
            "parse": {"format": report.format, "records": report.total,
                      "used": len(report.entries), "warnings": report.warnings},
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
        if not self.store.save(incident_id, digest, result):
            return {**self.store.get(incident_id)["result"], "replayed": True}
        log.info("incident diagnosed", extra={"incident_id": incident_id, "cause": d.cause_id,
                                              "severity": d.severity, "escalate": d.escalate,
                                              "records": report.total,
                                              "latency_ms": result["latency_ms"]})
        return {**result, "replayed": False}

    def get(self, incident_id: str) -> dict[str, Any]:
        row = self.store.get(incident_id)
        if row is None:
            raise NotFound(incident_id)
        return row["result"]

    def resolve(self, incident_id: str, actual_cause: str, notes: str) -> dict[str, Any]:
        if actual_cause not in CAUSES:
            raise ValueError(f"unknown cause {actual_cause!r}")
        if not self.store.resolve(incident_id, actual_cause, redact(notes)):
            raise NotFound(incident_id)
        return self.get(incident_id)
