from integration_triage.redact import leaked, redact


def test_api_keys_bearer_tokens_jwts_and_emails_are_redacted():
    text = ("key sk_live_abcdef123456 and Bearer abcdefgh12345678 and "
            "eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM and me@corp.com and whsec_ZZZZZZ9999")
    out = redact(text)
    for secret in ("sk_live_abcdef123456", "abcdefgh12345678", "eyJhbGciOi", "me@corp.com",
                   "whsec_ZZZZZZ9999"):
        assert secret not in out


def test_key_value_secrets_are_redacted_but_prose_is_not():
    assert "hunter22xx" not in redact("password: hunter22xx")
    assert redact("the token expired yesterday") == "the token expired yesterday"


def test_short_dashboard_key_prefixes_survive():
    assert "sk_live_ab12" in redact("key sk_live_ab12... returned 401")


def test_redact_is_idempotent():
    once = redact("Bearer abcdefgh12345678")
    assert redact(once) == once


def test_leaked_reports_which_secrets_remain():
    assert leaked("contains sk_live_x1", ["sk_live_x1", "nope"]) == ["sk_live_x1"]
