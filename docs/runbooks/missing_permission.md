# Connected account lacks a permission the action needs

`missing_permission`  |  default severity: sev3  |  needs an engineer: no  |  basis: general-practice

## How to confirm
403 from the third-party app with an insufficient-permission or scope message and no expiry wording.

## What to tell the customer
1. Grant the missing permission to the connected account in the third-party app, or reconnect with the required scopes.
2. Retry the call.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls (for example <ids>) were rejected by the third-party app with 403 insufficient permissions. The connected account does not have the permission this action needs, so this is an access setting rather than an expired login.

## Escalate when
The permission is granted in the third-party app and the 403 persists.
