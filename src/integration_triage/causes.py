"""The cause catalog: what can go wrong, how to confirm it, what to tell the customer.

`source` says where each entry's behaviour comes from, so nothing here pretends to be inside
knowledge of any vendor:
  public-docs       behaviour quoted from Merge's public Agent Handler FAQ
                    (https://docs.merge.dev/merge-agent-handler/resources/faq)
  general-practice  standard HTTP / OAuth / webhook behaviour that holds for most platforms
  illustrative      a pattern invented for this project; error strings are examples only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import LogEntry


@dataclass(frozen=True)
class Cause:
    id: str
    title: str
    severity: str          # default severity: sev1 page on-call, sev2 same-day, sev3 normal
    escalate: bool         # does a human engineer need to look at this?
    source: str
    confirm: str           # how a support engineer confirms it
    finding: str           # customer-facing explanation; {fields} filled from the evidence
    steps: tuple[str, ...]  # what the customer should do
    escalate_when: str


CAUSES: dict[str, Cause] = {c.id: c for c in (
    Cause(
        "key_scope_mismatch", "API key not scoped to the requested user", "sev3", False,
        "public-docs",
        "404 with the message 'Resource not in API key scope.' on tool or MCP calls whose user "
        "ID is outside the key's allowed users. It is a 404, not a 403, on purpose, so scoped "
        "keys cannot be used to discover whether other users exist.",
        "{n} calls between {first} and {last} UTC returned 404 \"Resource not in API key "
        "scope.\" (for example {ids}). That response means the key in use is not allowed to "
        "act for the user ID in the request. It does not mean the resource is missing.",
        ("Check which user ID is in the request URL and which users the key is scoped to.",
         "Use the user-scoped key that covers that user, or an organization-wide key if the "
         "call is not per-user.", "Retry once the key and user ID match."),
        "The key is scoped correctly, the user ID matches, and the 404 still appears.",
    ),
    Cause(
        "billing_limit", "Free-plan usage limit reached", "sev3", False, "public-docs",
        "HTTP 402 with the error code billing_limit_reached. Credits are used by every "
        "tools/call, including failed and blocked calls and calls made with test keys; "
        "tools/list is free.",
        "{n} calls since {first} UTC returned HTTP 402 with billing_limit_reached (for example "
        "{ids}). On the Free plan this means the monthly credits are used up, and it clears at "
        "the next billing cycle. Failed and blocked calls also use a credit, and so do calls "
        "made with test keys.",
        ("Check credit usage in the dashboard.",
         "Upgrade to a paid plan to keep calls flowing before the next cycle.",
         "Stop automatic retries on 402, because each retry can use another credit."),
        "Credit usage looks far below the plan allowance.",
    ),
    Cause(
        "rate_limited", "Per-user rate limit hit", "sev3", False, "public-docs",
        "HTTP 429 responses, usually with a Retry-After header. Per-user limits are enforced "
        "per minute and cannot be changed self-serve.",
        "{n} calls between {first} and {last} UTC returned HTTP 429 (for example {ids}); the "
        "longest Retry-After was {retry}s. Per-user rate limits apply per minute, so bursts "
        "from a single user trip them first.",
        ("Wait for the Retry-After period, then retry with exponential backoff and jitter.",
         "Queue or spread bursts per user instead of firing them at once.",
         "If you need a higher limit, reply with your usage pattern and I will take the "
         "request to our team."),
        "429s appear at volumes well below the documented limits, or never clear.",
    ),
    Cause(
        "invalid_api_key", "Invalid, revoked or rotated API key", "sev3", False,
        "public-docs",
        "401 with an invalid-key message. Rotating a production key invalidates the old key "
        "immediately, so a different key succeeding in the same window points to rotation.",
        "{n} calls between {first} and {last} UTC returned 401 for key {prefix}... (for "
        "example {ids}). {rotation_note}",
        ("Update the key in every backend service, worker and scheduled job.",
         "Check that you are using the right environment (test vs production).",
         "Retry once the new key is deployed everywhere."),
        "A key the customer confirms is valid and current is still rejected.",
    ),
    Cause(
        "end_user_auth_expired", "End-user authorization to the third-party app expired",
        "sev3", False, "general-practice",
        "401/403 coming back from the third-party app (upstream status 401/403) with an "
        "expired or revoked token message, concentrated on specific users.",
        "{n} calls for {users} user(s) between {first} and {last} UTC (for example {ids}) "
        "failed because the third-party authorization has expired or been revoked, so the "
        "connected app is refusing the calls.",
        ("Ask the affected user(s) to re-authorize the connection through the auth flow.",
         "Retry after re-authorizing.",
         "If many users expire at once, tell me and I will check for a wider cause."),
        "Re-authorization succeeds but the same error returns straight away.",
    ),
    Cause(
        "missing_permission", "Connected account lacks a permission the action needs", "sev3",
        False, "general-practice",
        "403 from the third-party app with an insufficient-permission or scope message and no "
        "expiry wording.",
        "{n} calls (for example {ids}) were rejected by the third-party app with 403 "
        "insufficient permissions. The connected account does not have the permission this "
        "action needs, so this is an access setting rather than an expired login.",
        ("Grant the missing permission to the connected account in the third-party app, or "
         "reconnect with the required scopes.", "Retry the call."),
        "The permission is granted in the third-party app and the 403 persists.",
    ),
    Cause(
        "upstream_outage", "Third-party service outage", "sev2", True, "general-practice",
        "Several 5xx responses (502/503/504 or upstream 5xx) across multiple users in the same "
        "window. Check the third-party's status page and the incident channel.",
        "{n} calls across {users} users between {first} and {last} UTC returned 5xx errors "
        "from the third-party service (for example {ids}). Several unrelated users failing in "
        "the same window points to a problem on the third-party side rather than your setup.",
        ("Check the third-party service's status page.",
         "Retry with backoff rather than in a tight loop.",
         "Hold off on reconnecting accounts until the third-party service recovers."),
        "Always: confirm with the incident channel and the status page before replying "
        "'it's them'.",
    ),
    Cause(
        "security_block", "Call blocked by a security or guardrail rule", "sev3", False,
        "public-docs",
        "Calls stopped before the third party with a security error. Blocking rules stop the "
        "call; redaction rules replace values before the model sees them. Blocked calls still "
        "use a credit.",
        "{n} calls (for example {ids}) were stopped by a security rule before they reached "
        "the third-party app. The rule is doing what it was configured to do, so this is a "
        "configuration question rather than an outage.",
        ("Open the audit trail and tool call logs to see which rule fired.",
         "Use the rule tester to check the rule against the payload.",
         "Adjust the rule or the payload, then retry."),
        "No rule explains the block, or the rule tester says the call should pass.",
    ),
    Cause(
        "platform_latency", "Sustained added latency on the platform side", "sev2", True,
        "public-docs",
        "Successful calls whose time outside the third-party call (total minus third_party) is "
        "above 500 ms on several calls. Typical overhead is 50-200 ms; sustained overhead "
        "above 500 ms should be reported with tool call IDs.",
        "{n} successful calls between {first} and {last} UTC spent a median of {median_ms} ms "
        "outside the third-party call (for example {ids}). Typical added time is 50-200 ms, "
        "so this is worth a closer look.",
        ("Keep the tool call IDs above so we can trace them.",
         "Tell me if it is still happening so we can compare against fresh calls."),
        "Always: this needs an engineer, with tool call IDs.",
    ),
    Cause(
        "slow_third_party", "Slow response from the third-party app", "sev3", False,
        "public-docs",
        "Slow calls where most of the time is the third_party segment of the latency breakdown "
        "and platform overhead is normal.",
        "{n} slow calls between {first} and {last} UTC (for example {ids}) spent a median of "
        "{median_ms} ms waiting on the third-party app. The time added on our side was "
        "normal.",
        ("Request smaller pages or fewer fields per call.",
         "Cache results in your agent runtime, because tool results are not cached "
         "server-side.", "Set client timeouts that allow for the third-party's response time."),
        "Overhead outside the third-party call is above 500 ms.",
    ),
    Cause(
        "pagination_loop", "Client re-requests the same page cursor", "sev3", False,
        "general-practice",
        "The same cursor value sent on 3 or more consecutive requests to one path, usually "
        "returning 200s.",
        "{n} requests to {path} between {first} and {last} UTC (for example {ids}) used the "
        "same cursor {cursor}, so the same page is being fetched over and over.",
        ("Use the next-page cursor from the latest response, not the one you sent.",
         "Stop paging when the response returns no next cursor."),
        "The client uses the returned cursor and still gets the same page back.",
    ),
    Cause(
        "webhook_signature", "Webhook signature verification failing on the receiver", "sev3",
        False, "general-practice",
        "Several webhook deliveries rejected with a signature mismatch.",
        "{n} webhook deliveries between {first} and {last} UTC (for example {ids}) failed "
        "signature verification. This is most often a signature computed over a parsed and "
        "re-serialized body instead of the raw request bytes, or a secret from another "
        "environment.",
        ("Compute the signature over the raw request body, before any JSON parsing.",
         "Compare with a constant-time function.",
         "Check that the signing secret matches the environment sending the webhook."),
        "Raw-body verification with the right secret still fails.",
    ),
    Cause(
        "insufficient_data", "Not enough information to diagnose", "sev3", False,
        "general-practice",
        "No log lines, or only healthy ones, and no pattern to match.",
        "I could not find failing calls that explain what you are seeing in the information I "
        "have so far.",
        ("Send one failing request ID and the UTC time it happened.",
         "Tell us what you expected and what you got instead.",
         "Tell us whether anything changed on your side (keys, deploys, plan) recently."),
        "n/a",
    ),
    Cause(
        "unknown", "Failures with no known pattern", "sev2", True, "general-practice",
        "Failing calls exist but no catalog pattern fits.",
        "{n} calls between {first} and {last} UTC are failing (for example {ids}) in a way "
        "I cannot yet match to a known cause, so I am escalating it with the details.",
        ("Tell me when it started and whether anything changed on your side.",
         "Send one failing request ID if you have others outside this window."),
        "Always.",
    ),
)}

# Tie-break order when two causes score equally.
PRIORITY: tuple[str, ...] = (
    "upstream_outage", "security_block", "billing_limit", "key_scope_mismatch",
    "invalid_api_key", "platform_latency", "rate_limited", "missing_permission",
    "end_user_auth_expired", "webhook_signature", "pagination_loop", "slow_third_party",
)


@dataclass(frozen=True)
class Match:
    evidence: list[LogEntry]
    base: float
    detail: dict


Matcher = Callable[[list[LogEntry], str], "Match | None"]


def _msg(e: LogEntry) -> str:
    return e.message.lower()


def m_key_scope(entries, ticket):
    ev = [e for e in entries if e.status == 404 and "not in api key scope" in _msg(e)]
    return Match(ev, 0.95, {}) if ev else None


def m_billing(entries, ticket):
    ev = [e for e in entries if e.status == 402 or e.error_code == "billing_limit_reached"]
    return Match(ev, 0.97, {}) if ev else None


def m_rate_limited(entries, ticket):
    ev = [e for e in entries if e.status == 429]
    if len(ev) < 2 and not any(e.retry_after for e in ev):
        return None
    retry = max((e.retry_after or 0 for e in ev), default=0)
    return Match(ev, 0.92, {"retry": retry})


def m_invalid_key(entries, ticket):
    def own_401(e: LogEntry) -> bool:   # the platform itself said 401, not the third party
        return e.status == 401 and e.upstream_status is None and e.source == "api"

    def says_key(e: LogEntry) -> bool:
        m = _msg(e)
        return (e.error_code == "invalid_api_key" or "invalid api key" in m
                or "revoked" in m or "api key" in m)

    own = [e for e in entries if own_401(e)]
    ev = [e for e in own if says_key(e)]
    generic = not ev          # a bare 401 still points at the credential, with less certainty
    ev = ev or own
    if not ev:
        return None
    bad = {e.key_prefix for e in ev if e.key_prefix}
    other_ok = {e.key_prefix for e in entries if e.status < 400 and e.key_prefix} - bad
    rotated = bool(other_ok) or "rotat" in ticket.lower()
    prefix = next(iter(sorted(bad)), "(unknown)")
    base = 0.7 if generic else (0.9 if rotated else 0.75)
    return Match(ev, base, {"rotated": rotated, "prefix": prefix, "generic": generic})


_EXPIRY = ("token expired", "expired", "reauthor", "re-authoriz", "revoked", "refresh token")
_PERMISSION = ("permission", "insufficient", "scope", "not authorized to", "forbidden")


def m_auth_expired(entries, ticket):
    ev = [e for e in entries
          if e.status in (401, 403) and (e.upstream_status in (401, 403))
          and any(w in _msg(e) for w in _EXPIRY)
          and not any(w in _msg(e) for w in ("permission", "insufficient"))]
    return Match(ev, 0.88, {}) if ev else None


def m_permission(entries, ticket):
    ev = [e for e in entries
          if e.status == 403 and e.upstream_status == 403
          and any(w in _msg(e) for w in _PERMISSION)
          and not any(w in _msg(e) for w in ("expired", "reauthor", "revoked"))]
    return Match(ev, 0.86, {}) if ev else None


def m_outage(entries, ticket):
    ev = [e for e in entries
          if e.status in (502, 503, 504) or (e.upstream_status or 0) >= 500]
    users = {e.user_id for e in ev if e.user_id}
    if len(ev) < 3 or len(users) < 2:
        return None
    return Match(ev, 0.9, {})


def m_security(entries, ticket):
    ev = [e for e in entries
          if (e.error_code or "").startswith("security") or "blocked by" in _msg(e)
          or "guardrail" in _msg(e)]
    return Match(ev, 0.9, {}) if ev else None


def m_platform_latency(entries, ticket):
    ev = [e for e in entries if not e.failed and (e.overhead_ms or 0) > 500]
    if len(ev) < 3:
        return None
    ov = sorted(e.overhead_ms or 0 for e in ev)
    return Match(ev, 0.85, {"median_ms": ov[len(ov) // 2]})


def m_slow_third_party(entries, ticket):
    ev = [e for e in entries
          if not e.failed and e.breakdown.get("third_party", 0) >= 1000
          and (e.overhead_ms or 0) <= 500]
    if len(ev) < 3:
        return None
    tp = sorted(e.breakdown["third_party"] for e in ev)
    return Match(ev, 0.85, {"median_ms": tp[len(tp) // 2]})


def m_pagination(entries, ticket):
    groups: dict[tuple[str, str], list[LogEntry]] = {}
    for e in entries:
        if e.cursor:
            groups.setdefault((e.path, e.cursor), []).append(e)
    loops = [g for g in groups.values() if len(g) >= 3]
    if not loops:
        return None
    worst = max(loops, key=len)
    return Match(worst, 0.88, {"path": worst[0].path, "cursor": worst[0].cursor})


def m_webhook(entries, ticket):
    ev = [e for e in entries if e.source == "webhook"
          and (e.error_code == "signature_mismatch" or "signature" in _msg(e))]
    return Match(ev, 0.9, {}) if len(ev) >= 2 else None


MATCHERS: dict[str, Matcher] = {
    "key_scope_mismatch": m_key_scope,
    "billing_limit": m_billing,
    "rate_limited": m_rate_limited,
    "invalid_api_key": m_invalid_key,
    "end_user_auth_expired": m_auth_expired,
    "missing_permission": m_permission,
    "upstream_outage": m_outage,
    "security_block": m_security,
    "platform_latency": m_platform_latency,
    "slow_third_party": m_slow_third_party,
    "pagination_loop": m_pagination,
    "webhook_signature": m_webhook,
}
