# Sustained added latency on the platform side

`platform_latency`  |  default severity: sev2  |  needs an engineer: yes  |  basis: public-docs

## How to confirm
Successful calls whose time outside the third-party call (total minus third_party) is above 500 ms on several calls. Typical overhead is 50-200 ms; sustained overhead above 500 ms should be reported with tool call IDs.

## What to tell the customer
1. Keep the tool call IDs above so we can trace them.
2. Tell me if it is still happening so we can compare against fresh calls.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> successful calls between <first> and <last> UTC spent a median of <median_ms> ms outside the third-party call (for example <ids>). Typical added time is 50-200 ms, so this is worth a closer look.

## Escalate when
Always: this needs an engineer, with tool call IDs.
