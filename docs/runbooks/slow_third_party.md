# Slow response from the third-party app

`slow_third_party`  |  default severity: sev3  |  needs an engineer: no  |  basis: public-docs

## How to confirm
Slow calls where most of the time is the third_party segment of the latency breakdown and platform overhead is normal.

## What to tell the customer
1. Request smaller pages or fewer fields per call.
2. Cache results in your agent runtime, because tool results are not cached server-side.
3. Set client timeouts that allow for the third-party's response time.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> slow calls between <first> and <last> UTC (for example <ids>) spent a median of <median_ms> ms waiting on the third-party app. The time added on our side was normal.

## Escalate when
Overhead outside the third-party call is above 500 ms.
