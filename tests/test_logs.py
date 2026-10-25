import pytest

from integration_triage.logs import parse_entry, parse_jsonl


def test_nested_error_and_headers_are_understood():
    e = parse_entry({"request_id": "a", "status": 429, "headers": {"Retry-After": "12"},
                     "error": {"code": "slow", "message": "Too fast"}})
    assert e.retry_after == 12 and e.error_code == "slow" and e.message == "Too fast"


def test_missing_required_fields_are_rejected_with_the_line_number():
    with pytest.raises(ValueError, match="line 2"):
        parse_jsonl('{"request_id":"a","status":200}\n{"status":500}')


def test_bad_json_is_rejected_with_the_line_number():
    with pytest.raises(ValueError, match="line 1"):
        parse_jsonl("not json")


def test_entries_are_returned_in_time_order_and_blank_lines_skipped():
    out = parse_jsonl('{"request_id":"b","status":200,"ts":"2026-01-02"}\n\n'
                      '{"request_id":"a","status":200,"ts":"2026-01-01"}')
    assert [e.request_id for e in out] == ["a", "b"]


def test_overhead_is_total_minus_third_party():
    e = parse_entry({"request_id": "a", "status": 200, "latency_ms": 900,
                     "breakdown": {"third_party": 300}})
    assert e.overhead_ms == 600
    assert parse_entry({"request_id": "b", "status": 200}).overhead_ms is None
