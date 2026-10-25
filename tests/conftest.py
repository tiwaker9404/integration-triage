from integration_triage.models import LogEntry


def entry(request_id="r1", status=200, **kw) -> LogEntry:
    return LogEntry(request_id=request_id, status=status, ts=kw.pop("ts", "2026-10-20T14:00:00Z"), **kw)


def many(n, status, prefix="x", **kw):
    return [entry(f"{prefix}{i}", status, ts=f"2026-10-20T14:00:{i:02d}Z", **kw) for i in range(n)]
