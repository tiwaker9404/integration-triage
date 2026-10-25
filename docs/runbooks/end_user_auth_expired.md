# End-user authorization to the third-party app expired

`end_user_auth_expired`  |  default severity: sev3  |  needs an engineer: no  |  basis: general-practice

## How to confirm
401/403 coming back from the third-party app (upstream status 401/403) with an expired or revoked token message, concentrated on specific users.

## What to tell the customer
1. Ask the affected user(s) to re-authorize the connection through the auth flow.
2. Retry after re-authorizing.
3. If many users expire at once, tell me and I will check for a wider cause.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls for <users> user(s) between <first> and <last> UTC (for example <ids>) failed because the third-party authorization has expired or been revoked, so the connected app is refusing the calls.

## Escalate when
Re-authorization succeeds but the same error returns straight away.
