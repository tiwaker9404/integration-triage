# Third-party service outage

`upstream_outage`  |  default severity: sev2  |  needs an engineer: yes  |  basis: general-practice

## How to confirm
Several 5xx responses (502/503/504 or upstream 5xx) across multiple users in the same window. Check the third-party's status page and the incident channel.

## What to tell the customer
1. Check the third-party service's status page.
2. Retry with backoff rather than in a tight loop.
3. Hold off on reconnecting accounts until the third-party service recovers.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls across <users> users between <first> and <last> UTC returned 5xx errors from the third-party service (for example <ids>). Several unrelated users failing in the same window points to a problem on the third-party side rather than your setup.

## Escalate when
Always: confirm with the incident channel and the status page before replying 'it's them'.
