# Operations

## Configuration (environment variables, validated at startup)

| Variable | Default | Notes |
|---|---|---|
| `TRIAGE_ENV` | `dev` | `prod` requires `TRIAGE_API_KEYS` and hides `/docs` |
| `TRIAGE_API_KEYS` | empty | comma-separated, 16+ characters each |
| `TRIAGE_DB_PATH` | `data/triage.db` | SQLite file; only redacted text is stored |
| `TRIAGE_MAX_BODY_MB` | `20` | larger requests get `413` |
| `TRIAGE_MAX_ENTRIES` | `100000` | more records gets a "filter to the incident window" error |
| `TRIAGE_RATE_LIMIT_PER_MIN` | `120` | per API key |
| `TRIAGE_DOCS` | `1` in dev, `0` in prod | interactive docs at `/docs` |

## Day to day

- **Engineering queue:** `GET /v1/incidents?escalated=true`. Each item carries the escalation
  packet: evidence table, severity, page-on-call flag, and what support already told the customer.
- **Close the loop:** after resolving an incident, `POST /v1/incidents/{id}/resolution` with the
  real cause. `GET /v1/stats` then reports `diagnosis_accuracy_on_resolved`, the number to watch.
- **A miss:** add the incident (redacted) to `wild_cases.jsonl`, fix the matcher, and let
  `triage eval --check` prove nothing else regressed.
- **Rotate API keys:** add the new key to `TRIAGE_API_KEYS`, restart, move clients over, remove
  the old key, restart.
- **Backup:** `sqlite3 data/triage.db ".backup backup.db"` works while running.
- **Logs:** JSON on stdout with `request_id`; ticket text and logs are never written to them.

## Limits

One process (SQLite + in-memory rate limiter). Scaling out needs Postgres and a shared limiter.
No TLS: run behind a reverse proxy to expose it beyond localhost.
