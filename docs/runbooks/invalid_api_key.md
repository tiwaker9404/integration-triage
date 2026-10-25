# Invalid, revoked or rotated API key

`invalid_api_key`  |  default severity: sev3  |  needs an engineer: no  |  basis: public-docs

## How to confirm
401 with an invalid-key message. Rotating a production key invalidates the old key immediately, so a different key succeeding in the same window points to rotation.

## What to tell the customer
1. Update the key in every backend service, worker and scheduled job.
2. Check that you are using the right environment (test vs production).
3. Retry once the new key is deployed everywhere.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls between <first> and <last> UTC returned 401 for key <prefix>... (for example <ids>). <rotation_note>

## Escalate when
A key the customer confirms is valid and current is still rejected.
