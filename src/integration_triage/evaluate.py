"""Score the whole pipeline (diagnose -> reply -> packet) on the labelled incident cases."""

from __future__ import annotations

import json
from importlib import resources
from statistics import fmean
from typing import Any

from .checks import reply_problems
from .compose import customer_reply, escalation_packet
from .diagnose import diagnose
from .logs import parse_entry
from .redact import leaked

# metric -> largest allowed drop versus the baseline
MAX_DROP = {
    "cause_accuracy": 0.03,
    "hard_cause_accuracy": 0.10,
    "wild_cause_accuracy": 0.10,
    "escalation_correct": 0.03,
    "escalation_recall": 0.0,
    "evidence_valid": 0.0,
    "no_secret_leak": 0.0,
    "reply_ok": 0.03,
}


def load_cases() -> list[dict[str, Any]]:
    """Generated cases (cases.jsonl) plus hand-written 'wild' ones (wild_cases.jsonl)."""
    rows: list[dict[str, Any]] = []
    for name in ("cases.jsonl", "wild_cases.jsonl"):
        path = resources.files("integration_triage") / "data" / name
        rows += [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]
    return rows


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    entries = [parse_entry(r) for r in case["logs"]]
    d = diagnose(sorted(entries, key=lambda e: e.ts), case["ticket"])
    reply = customer_reply(d)
    packet = escalation_packet(d, case["ticket"])
    gold = case["gold"]
    ids = {e.request_id for e in entries}
    evidence_ok = all(e.request_id in ids for e in d.evidence) and (
        bool(d.evidence) or d.cause_id == "insufficient_data")
    return {
        "predicted": d.cause_id, "gold": gold["cause"], "escalate": d.escalate,
        "gold_escalate": gold["escalate"], "confidence": d.confidence,
        "cause_ok": d.cause_id == gold["cause"],
        "escalation_ok": d.escalate == gold["escalate"],
        "evidence_ok": evidence_ok,
        "leaks": leaked(reply, gold["secrets"]) + leaked(packet, gold["secrets"]),
        "reply_problems": reply_problems(reply, d, gold["secrets"]),
        "kind": case["kind"],
    }


def run_eval() -> dict[str, Any]:
    results = {c["id"]: run_case(c) for c in load_cases()}
    rows = list(results.values())
    must = [r for r in rows if r["gold_escalate"]]
    hard = [r for r in rows if r["kind"] == "hard"]
    wild = [r for r in rows if r["kind"] == "wild"]
    metrics = {
        "cause_accuracy": fmean(r["cause_ok"] for r in rows),
        "hard_cause_accuracy": fmean(r["cause_ok"] for r in hard) if hard else 1.0,
        "wild_cause_accuracy": fmean(r["cause_ok"] for r in wild) if wild else 1.0,
        "escalation_correct": fmean(r["escalation_ok"] for r in rows),
        "escalation_recall": fmean(r["escalate"] for r in must) if must else 1.0,
        "evidence_valid": fmean(r["evidence_ok"] for r in rows),
        "no_secret_leak": fmean(not r["leaks"] for r in rows),
        "reply_ok": fmean(not r["reply_problems"] for r in rows),
    }
    return {"n": len(rows), "metrics": {k: round(v, 4) for k, v in metrics.items()},
            "cases": results}


def check(baseline: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    rows, passed = [], True
    for metric, limit in MAX_DROP.items():
        b, c = baseline["metrics"].get(metric), report["metrics"].get(metric)
        if b is None or c is None:
            continue
        delta = round(c - b, 4)
        bad = delta < -limit - 1e-9
        passed &= not bad
        rows.append({"metric": metric, "baseline": b, "candidate": c, "delta": delta,
                     "limit": limit, "status": "FAIL" if bad else "ok"})
    return {"passed": passed, "rows": rows}


def render(report: dict[str, Any]) -> str:
    lines = [f"cases: {report['n']}", "", "| metric | score |", "|---|---|"]
    lines += [f"| {k} | {v:.3f} |" for k, v in report["metrics"].items()]
    misses = [(cid, r) for cid, r in report["cases"].items() if not r["cause_ok"]]
    if misses:
        lines += ["", "wrong cause:"]
        lines += [f"- {cid}: predicted {r['predicted']}, expected {r['gold']}"
                  for cid, r in misses]
    return "\n".join(lines)
