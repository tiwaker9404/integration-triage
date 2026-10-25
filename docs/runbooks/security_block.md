# Call blocked by a security or guardrail rule

`security_block`  |  default severity: sev3  |  needs an engineer: no  |  basis: public-docs

## How to confirm
Calls stopped before the third party with a security error. Blocking rules stop the call; redaction rules replace values before the model sees them. Blocked calls still use a credit.

## What to tell the customer
1. Open the audit trail and tool call logs to see which rule fired.
2. Use the rule tester to check the rule against the payload.
3. Adjust the rule or the payload, then retry.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls (for example <ids>) were stopped by a security rule before they reached the third-party app. The rule is doing what it was configured to do, so this is a configuration question rather than an outage.

## Escalate when
No rule explains the block, or the rule tester says the call should pass.
