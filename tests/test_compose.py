from conftest import entry, many

from integration_triage.causes import CAUSES
from integration_triage.checks import MAX_WORDS, reply_problems
from integration_triage.compose import customer_reply, escalation_packet, runbook_entry
from integration_triage.diagnose import diagnose

KEY = "sk_live_SUPERSECRET123456"


def leaky_case():
    rows = many(4, 401, key_prefix="sk_live_ab12", error_code="invalid_api_key",
                message=f"Invalid API key: {KEY}")
    return diagnose(rows, f"my key is {KEY}"), f"my key is {KEY}"


def test_replies_and_packets_never_contain_the_secret():
    d, ticket = leaky_case()
    assert KEY not in customer_reply(d)
    assert KEY not in escalation_packet(d, ticket)


def test_reply_cites_request_ids_and_gives_numbered_steps():
    d, _ = leaky_case()
    reply = customer_reply(d)
    assert d.evidence[0].request_id in reply and "1)" in reply
    assert reply_problems(reply, d, [KEY]) == []


def test_checker_flags_leaks_promises_blame_and_missing_steps():
    d, _ = leaky_case()
    bad = f"We guarantee a fix. It is your fault. Your key {KEY}."
    problems = " | ".join(reply_problems(bad, d, [KEY]))
    for expected in ("leaks secret", "overpromises", "blames the customer",
                     "no concrete next step", "cites no request ID"):
        assert expected in problems


def test_checker_flags_long_replies():
    d, _ = leaky_case()
    assert any("too long" in p for p in
               reply_problems("1) " + "word " * (MAX_WORDS + 5) + d.evidence[0].request_id, d))


def test_every_cause_has_a_runbook_and_a_reply_that_formats():
    for cid, c in CAUSES.items():
        assert c.steps and c.finding and c.confirm
        assert runbook_entry(cid).startswith(f"# {c.title}")
    d = diagnose(many(3, 500, message="boom"))
    assert "escalating" in customer_reply(d)


def test_escalations_say_so_and_non_escalations_do_not():
    boom = diagnose(many(3, 500, message="boom"))
    assert "engineering team" in customer_reply(boom)
    rate = diagnose(many(3, 429, retry_after=9))
    assert "engineering team" not in customer_reply(rate)


def test_packet_has_the_evidence_table_and_page_flag():
    rows = [entry(f"o{i}", 503, user_id=f"u{i % 3}", upstream_status=503,
                  ts=f"2026-10-20T14:00:{i:02d}Z") for i in range(6)]
    packet = escalation_packet(diagnose(rows), "everything is down")
    assert "**Page on-call:** YES" in packet
    assert "| o0 |" in packet and "everything is down" in packet


def test_insufficient_data_reply_asks_questions_instead_of_citing_logs():
    d = diagnose([])
    reply = customer_reply(d)
    assert "request ID" in reply and reply_problems(reply, d) == []
