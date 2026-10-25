# Per-user rate limit hit

`rate_limited`  |  default severity: sev3  |  needs an engineer: no  |  basis: public-docs

## How to confirm
HTTP 429 responses, usually with a Retry-After header. Per-user limits are enforced per minute and cannot be changed self-serve.

## What to tell the customer
1. Wait for the Retry-After period, then retry with exponential backoff and jitter.
2. Queue or spread bursts per user instead of firing them at once.
3. If you need a higher limit, reply with your usage pattern and I will take the request to our team.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls between <first> and <last> UTC returned HTTP 429 (for example <ids>); the longest Retry-After was <retry>s. Per-user rate limits apply per minute, so bursts from a single user trip them first.

## Escalate when
429s appear at volumes well below the documented limits, or never clear.
