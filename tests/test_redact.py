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


# ---- second layer: unknown key formats via entropy, without eating evidence ----
from integration_triage.redact import looks_secret  # noqa: E402


def test_unknown_key_formats_are_caught_by_entropy():
    for key in ("mg_9fK2xQ7pL4vT8nR3sW6yZ1bC5dE0aH2j", "Zt8Qw3Lp0Vb7Nn2Rr5Yy9Kk4Hh1Gg6Ff",
                "lsv2" + "_pt_" + "0f1e2d3c4b5a69788796a5b4c3d2e1f0" + "_" + "fa4e0000ke"):
        assert key not in redact(f"my key is {key} thanks")


def test_vendor_key_shapes():
    for key in ("ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4", "xoxb-1234567890-abcdefghij",
                "AKIAABCDEFGHIJKLMNOP", "AIza" + "x" * 35):
        assert key not in redact(f"token {key}")


def test_ordinary_identifiers_survive():
    keep_me = ["0d4f6a1e-3c2b-4e8f-9a7d-1b2c3d4e5f60", "authorization_header_configuration_settings",
               "/Users/me/projects/integration-triage/src/logs.py", "order 1234567890123456"]
    for text in keep_me:
        assert redact(text) == text
    assert not looks_secret("aaaaaaaaaaaaaaaaaaaaaaaa1234")


def test_cited_request_ids_are_kept_even_if_they_look_random():
    rid = "req_01HZX3K8Q9T7VB2MP4WCN6R5JD"
    assert looks_secret(rid)
    assert rid in redact(f"see {rid}", keep=[rid])
    assert rid not in redact(f"see {rid}")


def test_pii_cards_need_luhn_and_phones_are_removed():
    out = redact("card 4111 1111 1111 1111 call (415) 555-0134 order #4471")
    assert "4111" not in out and "555-0134" not in out and "#4471" in out


def test_url_query_secrets_and_private_keys():
    assert "abcd1234efgh" not in redact("GET /x?api_key=abcd1234efgh&y=1")
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
    assert "MIIEow" not in redact(pem)
