# API key not scoped to the requested user

`key_scope_mismatch`  |  default severity: sev3  |  needs an engineer: no  |  basis: public-docs

## How to confirm
404 with the message 'Resource not in API key scope.' on tool or MCP calls whose user ID is outside the key's allowed users. It is a 404, not a 403, on purpose, so scoped keys cannot be used to discover whether other users exist.

## What to tell the customer
1. Check which user ID is in the request URL and which users the key is scoped to.
2. Use the user-scoped key that covers that user, or an organization-wide key if the call is not per-user.
3. Retry once the key and user ID match.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> calls between <first> and <last> UTC returned 404 "Resource not in API key scope." (for example <ids>). That response means the key in use is not allowed to act for the user ID in the request. It does not mean the resource is missing.

## Escalate when
The key is scoped correctly, the user ID matches, and the 404 still appears.
