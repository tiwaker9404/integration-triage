# Not enough information to diagnose

`insufficient_data`  |  default severity: sev3  |  needs an engineer: no  |  basis: general-practice

## How to confirm
No log lines, or only healthy ones, and no pattern to match.

## What to tell the customer
1. Send one failing request ID and the UTC time it happened.
2. Tell us what you expected and what you got instead.
3. Tell us whether anything changed on your side (keys, deploys, plan) recently.

## Reply macro (fill the <placeholders> from the log evidence)
> I could not find failing calls that explain what you are seeing in the information I have so far.

## Escalate when
n/a
