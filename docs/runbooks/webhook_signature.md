# Webhook signature verification failing on the receiver

`webhook_signature`  |  default severity: sev3  |  needs an engineer: no  |  basis: general-practice

## How to confirm
Several webhook deliveries rejected with a signature mismatch.

## What to tell the customer
1. Compute the signature over the raw request body, before any JSON parsing.
2. Compare with a constant-time function.
3. Check that the signing secret matches the environment sending the webhook.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> webhook deliveries between <first> and <last> UTC (for example <ids>) failed signature verification. This is most often a signature computed over a parsed and re-serialized body instead of the raw request bytes, or a secret from another environment.

## Escalate when
Raw-body verification with the right secret still fails.
