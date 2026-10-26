# Tool not available on this MCP connection

`tool_not_in_scope`  |  default severity: sev3  |  needs an engineer: no  |  basis: public-docs

## How to confirm
tools/call returns a JSON-RPC invalid-params error (-32602) inside an HTTP 200. Merge's MCP docs list this as the error when the tool is outside the connection's connectors scope; a tool name missing from the Tool Pack looks the same.

## What to tell the customer
1. Call tools/list on the same connection and copy the exact tool name it returns.
2. Add the connector or tool to the Tool Pack, or include it in ?connectors=.
3. Retry the call.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> tool calls between <first> and <last> UTC (for example <ids>) were rejected with an invalid-params error: the tool is not available on this connection. This usually means the tool is not in the Tool Pack, or the connection URL limits connectors with ?connectors= and leaves it out.

## Escalate when
The tool is listed by tools/list on the same connection and the call still fails.
