"""HTTP API for integration-triage.

    triage-serve                              # uvicorn on 0.0.0.0:8080, settings from the environment

    POST /v1/diagnose                         ticket + raw logs -> diagnosis, reply, packet
    GET  /v1/incidents                        history (?escalated=true for the engineering queue)
    GET  /v1/incidents/{id}                   one stored result
    POST /v1/incidents/{id}/resolution        record the actual cause (feeds accuracy stats)
    GET  /v1/stats                            volume, escalations, accuracy on resolved incidents
    GET  /v1/causes, /v1/runbooks/{cause_id}  the catalog and its runbooks
    GET  /healthz, /readyz                    probes
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from . import __version__
from .causes import CAUSES
from .compose import runbook_entry
from .config import Settings
from .service import Conflict, NotFound, TriageService

log = logging.getLogger("integration_triage")
_STD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Ticket text and logs are never passed to the logger."""

    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
               "msg": record.getMessage()}
        out.update({k: v for k, v in vars(record).items() if k not in _STD})
        return json.dumps(out, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log.handlers[:] = [handler]
    log.setLevel(level)
    log.propagate = False


class DiagnoseIn(BaseModel):
    ticket: str = Field(default="", max_length=20_000, description="The customer's message")
    logs: str = Field(default="", description="Raw request logs: JSON lines, JSON array or CSV")
    mapping: dict[str, str] | None = Field(default=None,
                                           description="Optional field -> dotted path overrides")
    incident_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,64}$",
                                    description="Your id; resending the same id is safe")


class ResolutionIn(BaseModel):
    actual_cause: str = Field(description="One of the ids from /v1/causes")
    notes: str = Field(default="", max_length=2000)


class RateLimiter:
    """Sliding one-minute window per caller, in-process (one worker)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, who: str) -> bool:
        cutoff = time.monotonic() - 60
        with self._lock:
            q = self._hits[who]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(time.monotonic())
            return True


def create_app(settings: Settings | None = None, service: TriageService | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or TriageService(settings)
    limiter = RateLimiter(settings.rate_limit_per_min)
    max_body = settings.max_body_mb * 1024 * 1024 + 64 * 1024  # logs + JSON envelope
    app = FastAPI(title="integration-triage", version=__version__,
                  docs_url="/docs" if settings.docs_enabled else None, redoc_url=None,
                  openapi_url="/openapi.json" if settings.docs_enabled else None)
    app.state.service = service

    @app.middleware("http")
    async def guard(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > max_body:
            response = JSONResponse({"detail": f"body larger than {settings.max_body_mb} MB"},
                                    status_code=413)
        else:
            response = await call_next(request)
        response.headers["x-request-id"] = rid
        log.info("request", extra={"request_id": rid, "method": request.method,
                                   "path": request.url.path, "status": response.status_code,
                                   "ms": int((time.perf_counter() - started) * 1000)})
        return response

    def caller(x_api_key: str | None = Header(default=None)) -> str:
        if settings.auth_required:
            if not x_api_key or not any(hmac.compare_digest(x_api_key, k)
                                        for k in settings.api_keys):
                raise HTTPException(401, "missing or invalid X-API-Key")
            who = "key:" + x_api_key[-4:]
        else:
            who = "anonymous"
        if not limiter.allow(who):
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})
        return who

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        ok = service.store.ping()
        return JSONResponse({"store": ok}, status_code=200 if ok else 503)

    @app.post("/v1/diagnose")
    def diagnose(body: DiagnoseIn, _: str = Depends(caller)) -> dict[str, Any]:
        if not body.ticket.strip() and not body.logs.strip():
            raise HTTPException(422, "send a ticket, logs, or both")
        if body.mapping:
            from .logs import ALIASES
            unknown = set(body.mapping) - set(ALIASES)
            if unknown:
                raise HTTPException(422, f"unknown mapping fields: {', '.join(sorted(unknown))}")
        try:
            return service.diagnose(body.ticket, body.logs, body.mapping, body.incident_id)
        except Conflict:
            raise HTTPException(409, "incident_id already used with different input") from None
        except ValueError as exc:  # unreadable or oversized logs
            raise HTTPException(422, str(exc)) from None

    @app.get("/v1/incidents")
    def incidents(escalated: bool | None = None, limit: int = Query(50, ge=1, le=500),
                  _: str = Depends(caller)) -> list[dict[str, Any]]:
        return service.store.list(escalated, limit)

    @app.get("/v1/incidents/{incident_id}")
    def incident(incident_id: str, _: str = Depends(caller)) -> dict[str, Any]:
        try:
            return service.get(incident_id)
        except NotFound:
            raise HTTPException(404, "unknown incident_id") from None

    @app.post("/v1/incidents/{incident_id}/resolution")
    def resolve(incident_id: str, body: ResolutionIn, _: str = Depends(caller)) -> dict[str, Any]:
        try:
            return service.resolve(incident_id, body.actual_cause, body.notes)
        except NotFound:
            raise HTTPException(404, "unknown incident_id") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/v1/stats")
    def stats(_: str = Depends(caller)) -> dict[str, Any]:
        return service.store.stats()

    @app.get("/v1/causes")
    def causes(_: str = Depends(caller)) -> list[dict[str, Any]]:
        return [{"id": c.id, "title": c.title, "severity": c.severity, "escalate": c.escalate,
                 "source": c.source} for c in CAUSES.values()]

    @app.get("/v1/runbooks/{cause_id}", response_class=PlainTextResponse)
    def runbook(cause_id: str, _: str = Depends(caller)) -> str:
        if cause_id not in CAUSES:
            raise HTTPException(404, "unknown cause_id")
        return runbook_entry(cause_id)

    return app


def main() -> None:  # pragma: no cover - thin wrapper around uvicorn
    import uvicorn

    configure_logging(os.environ.get("TRIAGE_LOG_LEVEL", "INFO"))
    try:
        Settings.from_env()
    except ValueError as exc:
        print(f"triage-serve: configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    uvicorn.run("integration_triage.api:create_app", factory=True,
                host=os.environ.get("TRIAGE_HOST", "0.0.0.0"),
                port=int(os.environ.get("TRIAGE_PORT", "8080")),
                workers=1, access_log=False, proxy_headers=True)
