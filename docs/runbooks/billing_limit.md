# Free-plan usage limit reached

`billing_limit`  |  default severity: sev3  |  needs an engineer: no  |  basis: public-docs

## How to confirm
HTTP 402 with the error code billing_limit_reached. Credits are used by every tools/call, including failed and blocked calls and calls made with test keys; tools/list is free.

## What to tell the customer
1. Check credit usage in the dashboard.
2. Upgrade to a paid plan to keep calls flowing before the next cycle.
3. Stop automatic retries on 402, because each retry can use another credit.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls since <first> UTC returned HTTP 402 with billing_limit_reached (for example <ids>). On the Free plan this means the monthly credits are used up, and it clears at the next billing cycle. Failed and blocked calls also use a credit, and so do calls made with test keys.

## Escalate when
Credit usage looks far below the plan allowance.
