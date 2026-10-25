# Client re-requests the same page cursor

`pagination_loop`  |  default severity: sev3  |  needs an engineer: no  |  basis: general-practice

## How to confirm
The same cursor value sent on 3 or more consecutive requests to one path, usually returning 200s.

## What to tell the customer
1. Use the next-page cursor from the latest response, not the one you sent.
2. Stop paging when the response returns no next cursor.

## Reply macro (fill the <placeholders> from the log evidence)
> <n> requests to <path> between <first> and <last> UTC (for example <ids>) used the same cursor <cursor>, so the same page is being fetched over and over.

## Escalate when
The client uses the returned cursor and still gets the same page back.
