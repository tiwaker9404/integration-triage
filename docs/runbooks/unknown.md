# Failures with no known pattern

`unknown`  |  default severity: sev2  |  needs an engineer: yes  |  basis: general-practice

## How to confirm
Failing calls exist but no catalog pattern fits.

## What to tell the customer
1. Tell me when it started and whether anything changed on your side.
2. Send one failing request ID if you have others outside this window.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls between <first> and <last> UTC are failing (for example <ids>) in a way I cannot yet match to a known cause, so I am escalating it with the details.

## Escalate when
Always.
