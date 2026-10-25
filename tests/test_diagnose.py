from conftest import entry, many

from integration_triage.diagnose import diagnose


def cause(entries, ticket=""):
    return diagnose(entries, ticket).cause_id


def test_each_documented_public_behaviour_is_recognised():
    scope = many(3, 404, message="Resource not in API key scope.")
    assert cause(scope) == "key_scope_mismatch"
    assert cause(many(3, 402, error_code="billing_limit_reached")) == "billing_limit"
    assert cause(many(3, 429, retry_after=30)) == "rate_limited"


def test_rotation_is_inferred_from_a_second_working_key_or_the_ticket():
    bad = many(3, 401, key_prefix="sk_live_old1", error_code="invalid_api_key")
    d = diagnose(bad + [entry("ok", 200, key_prefix="sk_live_new1")])
    assert d.cause_id == "invalid_api_key" and d.detail["rotated"] is True
    assert diagnose(bad).detail["rotated"] is False
    assert diagnose(bad, "we rotated our keys").detail["rotated"] is True


def test_a_bare_401_still_points_at_the_credential_but_with_lower_confidence():
    d = diagnose(many(4, 401, key_prefix="sk_live_q7w8", message="Authentication failed"))
    assert d.cause_id == "invalid_api_key" and d.detail["generic"] is True
    assert d.confidence < 0.8


def test_third_party_401_is_an_end_user_problem_not_an_api_key_problem():
    d = diagnose(many(3, 401, upstream_status=401, user_id="u1",
                      message="Third-party token expired"))
    assert d.cause_id == "end_user_auth_expired"


def test_403_wording_separates_permission_from_expiry():
    perm = many(3, 403, upstream_status=403, message="Insufficient permissions: missing scope")
    assert cause(perm) == "missing_permission"
    exp = many(3, 403, upstream_status=403, message="Token expired, reauthorize")
    assert cause(exp) == "end_user_auth_expired"


def test_an_outage_needs_several_failures_across_several_users():
    one_user = [entry(f"o{i}", 503, user_id="u1", upstream_status=503) for i in range(4)]
    assert cause(one_user) == "unknown"
    many_users = [entry(f"o{i}", 503, user_id=f"u{i}", upstream_status=503) for i in range(4)]
    assert cause(many_users) == "upstream_outage"


def test_outage_severity_scales_with_users_affected():
    three = [entry(f"o{i}", 503, user_id=f"u{i % 3}", upstream_status=503) for i in range(6)]
    two = [entry(f"o{i}", 503, user_id=f"u{i % 2}", upstream_status=503) for i in range(6)]
    assert diagnose(three).severity == "sev1" and diagnose(three).page_oncall
    assert diagnose(two).severity == "sev2" and not diagnose(two).page_oncall


def test_latency_blames_the_platform_only_when_overhead_is_high():
    slow_us = many(4, 200, latency_ms=1800, breakdown={"third_party": 400})
    slow_them = many(4, 200, latency_ms=3200, breakdown={"third_party": 3000})
    assert cause(slow_us) == "platform_latency" and diagnose(slow_us).escalate
    assert cause(slow_them) == "slow_third_party" and not diagnose(slow_them).escalate


def test_repeated_cursor_is_a_pagination_loop():
    rows = many(4, 200, path="/employees", cursor="cur_1")
    d = diagnose(rows)
    assert d.cause_id == "pagination_loop" and d.detail["cursor"] == "cur_1"


def test_webhook_signature_failures_are_not_mistaken_for_bad_keys():
    rows = many(3, 401, source="webhook", error_code="signature_mismatch")
    assert cause(rows) == "webhook_signature"


def test_dominant_cause_wins_when_signals_mix():
    mixed = many(8, 429, retry_after=30, user_id="u1") + [
        entry(f"b{i}", 502, user_id=f"u{i % 2}", upstream_status=502) for i in range(3)]
    d = diagnose(mixed)
    assert d.cause_id == "rate_limited"
    assert "upstream_outage" in dict(d.alternatives)


def test_no_logs_or_only_healthy_logs_means_ask_for_more_not_escalate():
    for logs in ([], many(5, 200)):
        d = diagnose(logs)
        assert d.cause_id == "insufficient_data" and not d.escalate


def test_failures_with_no_pattern_escalate():
    d = diagnose(many(3, 500, message="boom"))
    assert d.cause_id == "unknown" and d.escalate


def test_evidence_always_comes_from_the_supplied_logs():
    rows = many(5, 429, retry_after=5)
    d = diagnose(rows)
    assert {e.request_id for e in d.evidence} <= {e.request_id for e in rows}
