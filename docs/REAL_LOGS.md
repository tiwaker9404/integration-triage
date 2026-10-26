# Testing on real Merge Agent Handler errors

> **Status:** not yet run on a live account. Signup requires a company email, so everything below
> was verified against a local mock built from Merge's public docs. If you have a test key, this
> takes about two minutes, and I'd genuinely like to know how it does.

Goal: run the tool on errors Merge's platform actually returned, and report honestly what it got
right and wrong. Everything else in this repo was built from public docs and synthetic logs.

The platform details below (URLs, the MCP endpoint format, request IDs in Tool Call Logs) come
from Merge's public docs. I have not seen its dashboard or log export, so the capture script below
records the responses itself instead of relying on an export.

## Part A: set up a free account (15 min)

1. Sign up for Agent Handler on the free plan and open the dashboard.
2. **Create a test Registered User** (Registered Users page). Copy its ID.
3. **Create a Tool Pack** (Tool Packs page) and add any one connector. Copy the Tool Pack ID from
   the page URL. You do not need to authenticate the connector: nothing here needs a successful
   third-party call.
4. **Create a TEST access key** (Settings > API Keys). Test keys work with test users; the docs say
   test and production keys "don't mix". Never use a production key for this.

## Part B: capture real responses (5 min)

```bash
cd integration-triage
export AH_KEY='<test key>'
export AH_TOOL_PACK='<tool pack id>'
export AH_USER='<test registered user id>'
python scripts/capture_agent_handler.py
python scripts/capture_agent_handler.py --tool-call notion__search
```

Use a tool name that is not in your pack for `--tool-call`. The script makes about 3 calls per
scenario, half a second apart, and writes one file per scenario to `real/` (git-ignored):

| File | What it does | What the tool should say |
|---|---|---|
| `baseline.jsonl` | correct key, user and pack | not enough information (nothing is failing) |
| `wrong_key.jsonl` | the key with its last 6 characters changed | invalid or rotated API key |
| `unknown_user.jsonl` | a registered user ID that does not exist | a key-scope / not-found 404 (see below) |
| `tool_call.jsonl` | calls a tool outside the pack | tool not available on this MCP connection |

Only the first 8 characters of the key are written. Check with
`grep -c "$AH_KEY" real/*.jsonl`: every count must be 0.

## Part C: diagnose each one

```bash
triage diagnose --logs real/wrong_key.jsonl    --ticket "Every call returns 401 since we rotated keys"
triage diagnose --logs real/unknown_user.jsonl --ticket "404 for one of our users"
triage diagnose --logs real/tool_call.jsonl    --ticket "The agent says the Notion tool doesn't exist"
triage diagnose --logs real/baseline.jsonl     --ticket "Is anything wrong?"
```

Then cross-check in the dashboard: open Tool Call Logs and filter by one of the `request_id`
values the script printed. That proves the IDs in the escalation packet match Merge's own logs.

## Part D: record the results honestly

Write down, per scenario: the status and message Merge returned, what the tool diagnosed, and
whether that is right. Likely surprises:

- **Unknown user:** the FAQ's "Resource not in API key scope." 404 is for a user outside a
  *user-scoped* key. A user that does not exist at all may return a different status or message.
  If the tool says "unknown", that is a real gap; share the status and message and we will add
  a cause for it.
- **Wrong key:** the exact message may differ from the ones the matcher looks for. A bare 401 is
  still handled, at lower confidence.
- **Tool calls:** if the error code is not -32602, tell me what it was.

Add any case it got wrong to `src/integration_triage/data/wild_cases.jsonl` (no keys, no
personal data), fix the matcher, and run `triage eval --check`.

## Part E: clean up

Delete the test key in Settings > API Keys and run `unset AH_KEY`.

## What to say afterwards

Only what happened, for example: "Tested on 4 real Agent Handler error scenarios: 3 diagnosed
correctly; the 4th (nonexistent user) returned X, which I added as a new cause."
