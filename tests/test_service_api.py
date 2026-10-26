import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from integration_triage.api import JsonFormatter, create_app
from integration_triage.config import Settings
from integration_triage.evaluate import load_cases
from integration_triage.service import TriageService
from integration_triage.store import Store

KEY = "k" * 20
CASES = {c["id"]: c for c in load_cases()}


def logs_of(cid):
    return "\n".join(json.dumps(r) for r in CASES[cid]["logs"])


def make(settings=None, **kw):
    settings = settings or Settings(db_path=":memory:", **kw)
    return TestClient(create_app(settings, TriageService(settings, Store(":memory:"))))


def post(c, ticket="", logs="", key=None, **extra):
    headers = {"X-API-Key": key} if key else {}
    return c.post("/v1/diagnose", json={"ticket": ticket, "logs": logs, **extra}, headers=headers)


def test_health_ready_and_catalog():
    c = make()
    assert c.get("/healthz").json()["status"] == "ok"
    assert c.get("/readyz").json()["store"] is True
    assert len(c.get("/v1/causes").json()) >= 12
    assert c.get("/v1/runbooks/rate_limited").text.startswith("# ")
    assert c.get("/v1/runbooks/nope").status_code == 404


def test_diagnose_round_trip_and_history():
    c = make()
    case = CASES["case19"]
    body = post(c, case["ticket"], logs_of("case19"), incident_id="inc-1").json()
    assert body["cause"] == "upstream_outage" and body["page_oncall"] and body["escalation_packet"]
    assert body["parse"]["format"] == "jsonl" and body["parse"]["warnings"] == []
    assert c.get("/v1/incidents/inc-1").json()["cause"] == "upstream_outage"
    assert [i["incident_id"] for i in c.get("/v1/incidents?escalated=true").json()] == ["inc-1"]


def test_secrets_never_reach_the_response_or_the_store():
    c = make()
    case = CASES["case10"]
    secret = case["gold"]["secrets"][0]
    r = post(c, case["ticket"], logs_of("case10"), incident_id="s1")
    assert secret not in r.text
    assert secret not in json.dumps(c.app.state.service.store.get("s1"))


def test_idempotent_incident_ids():
    c = make()
    first = post(c, "x", logs_of("case01"), incident_id="dup").json()
    again = post(c, "x", logs_of("case01"), incident_id="dup").json()
    assert again["replayed"] and again["cause"] == first["cause"]
    assert post(c, "different", logs_of("case01"), incident_id="dup").status_code == 409


def test_resolution_feeds_accuracy_stats():
    c = make()
    post(c, "", logs_of("case01"), incident_id="a")       # key_scope_mismatch, correct
    post(c, "", logs_of("case07"), incident_id="b")
    c.post("/v1/incidents/a/resolution", json={"actual_cause": "key_scope_mismatch"})
    c.post("/v1/incidents/b/resolution", json={"actual_cause": "unknown", "notes": "was a bug"})
    stats = c.get("/v1/stats").json()
    assert stats["resolved"] == 2 and stats["diagnosis_accuracy_on_resolved"] == 0.5
    assert c.get("/v1/incidents/b").json()["resolution"]["diagnosis_correct"] is False
    assert c.post("/v1/incidents/a/resolution", json={"actual_cause": "nope"}).status_code == 422
    assert c.post("/v1/incidents/zz/resolution", json={"actual_cause": "unknown"}).status_code == 404


def test_messy_csv_with_warnings_through_the_api():
    c = make()
    csv_text = ("requestId,statusCode,timestamp,retryAfter\n"
                "a,429,2026-10-20 14:00:00,30\nb,429,2026-10-20 14:00:09,45\nc,bad,,\n")
    body = post(c, "throttled!", csv_text).json()
    assert body["cause"] == "rate_limited" and body["parse"]["format"] == "csv"
    assert "skipped 1 of 3" in body["parse"]["warnings"][0]


def test_input_validation():
    c = make()
    assert post(c).status_code == 422                                   # nothing to work with
    assert post(c, "hi", "%%% not logs").status_code == 422             # unreadable logs
    assert post(c, "hi", mapping={"colour": "x"}).status_code == 422
    assert post(c, "hi", incident_id="bad id!").status_code == 422


def test_body_size_limit_returns_413():
    c = make(max_body_mb=1)
    big = '{"request_id":"r","status":200}\n' * 40_000                 # ~1.3 MB
    assert post(c, "big", big).status_code == 413


def test_prod_requires_keys_and_hides_docs(monkeypatch):
    s = Settings(env="prod", api_keys=(KEY,), db_path=":memory:", docs_enabled=False)
    c = make(s)
    assert post(c, "hi").status_code == 401
    assert post(c, "hi", key="wrong-wrong-wrong-key").status_code == 401
    assert post(c, "hi", key=KEY).status_code == 200
    assert c.get("/docs").status_code == 404 and c.get("/healthz").status_code == 200
    monkeypatch.setenv("TRIAGE_ENV", "prod")
    monkeypatch.delenv("TRIAGE_API_KEYS", raising=False)
    with pytest.raises(ValueError, match="TRIAGE_API_KEYS"):
        Settings.from_env()
    monkeypatch.setenv("TRIAGE_API_KEYS", "short")
    with pytest.raises(ValueError, match="16"):
        Settings.from_env()


def test_rate_limit():
    c = make(rate_limit_per_min=2)
    assert [post(c, "hi").status_code for _ in range(3)] == [200, 200, 429]


def test_logs_are_json_and_never_contain_ticket_text(caplog):
    c = make()
    caplog.set_level(logging.INFO, logger="integration_triage")
    post(c, "my very private complaint", logs_of("case01"))
    lines = [JsonFormatter().format(r) for r in caplog.records]
    assert lines and not any("private complaint" in l for l in lines)


def test_large_log_is_fast():
    rows = [{"request_id": f"r{i}", "status": 200, "ts": f"2026-10-20T14:{i // 60 % 60:02d}:{i % 60:02d}Z",
             "user_id": f"u{i % 50}"} for i in range(20_000)]
    rows += [{"request_id": f"x{i}", "status": 429, "retry_after": 30, "user_id": "u1"} for i in range(30)]
    text = "\n".join(json.dumps(r) for r in rows)
    c = make()
    started = time.perf_counter()
    body = post(c, "slow?", text).json()
    assert body["cause"] == "rate_limited" and body["parse"]["records"] == 20_030
    assert time.perf_counter() - started < 5
