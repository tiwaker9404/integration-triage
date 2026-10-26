"""Incident history in SQLite: zero cost, zero infrastructure. Only redacted text is stored.

Resolutions (what the cause actually turned out to be) are what make the tool measurable on real
tickets: `stats()` reports diagnosis accuracy on every incident someone has resolved.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id   TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    input_hash    TEXT NOT NULL,
    cause         TEXT NOT NULL,
    severity      TEXT NOT NULL,
    escalate      INTEGER NOT NULL,
    result        TEXT NOT NULL,
    actual_cause  TEXT,
    resolved_at   TEXT,
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS incidents_escalate ON incidents (escalate, created_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._memory = None
        if path == ":memory:":
            self._memory = sqlite3.connect(path, check_same_thread=False)
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            if self._memory is None:
                c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        if self._memory is not None:
            with self._lock:
                yield self._memory
                self._memory.commit()
            return
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ping(self) -> bool:
        try:
            with self._conn() as c:
                c.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def get(self, incident_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT input_hash, result, actual_cause, resolved_at, notes "
                            "FROM incidents WHERE incident_id = ?", (incident_id,)).fetchone()
        if row is None:
            return None
        result = json.loads(row[1])
        if row[2]:
            result["resolution"] = {"actual_cause": row[2], "resolved_at": row[3],
                                    "notes": row[4] or "",
                                    "diagnosis_correct": row[2] == result["cause"]}
        return {"input_hash": row[0], "result": result}

    def save(self, incident_id: str, input_hash: str, result: dict[str, Any]) -> bool:
        with self._lock, self._conn() as c:
            cur = c.execute("INSERT OR IGNORE INTO incidents (incident_id, created_at, input_hash,"
                            " cause, severity, escalate, result) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (incident_id, result["created_at"], input_hash, result["cause"],
                             result["severity"], int(result["escalate"]), json.dumps(result)))
            return cur.rowcount == 1

    def resolve(self, incident_id: str, actual_cause: str, notes: str) -> bool:
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE incidents SET actual_cause = ?, resolved_at = ?, notes = ? "
                            "WHERE incident_id = ?", (actual_cause, now(), notes, incident_id))
            return cur.rowcount == 1

    def list(self, escalated: bool | None, limit: int) -> list[dict[str, Any]]:
        sql, args = "SELECT incident_id FROM incidents", []
        if escalated is not None:
            sql += " WHERE escalate = ?"
            args.append(int(escalated))
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            ids = [r[0] for r in c.execute(sql, args).fetchall()]
        return [self.get(i)["result"] for i in ids]

    def stats(self) -> dict[str, Any]:
        with self._conn() as c:
            total, esc, page = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(escalate), 0), "
                "COALESCE(SUM(severity = 'sev1'), 0) FROM incidents").fetchone()
            resolved, correct = c.execute(
                "SELECT COUNT(*), COALESCE(SUM(actual_cause = cause), 0) FROM incidents "
                "WHERE actual_cause IS NOT NULL").fetchone()
            by_cause = dict(c.execute("SELECT cause, COUNT(*) FROM incidents GROUP BY cause "
                                      "ORDER BY COUNT(*) DESC").fetchall())
        return {"incidents": total, "escalated": esc, "sev1": page, "resolved": resolved,
                "diagnosis_accuracy_on_resolved": round(correct / resolved, 3) if resolved else None,
                "by_cause": by_cause}
