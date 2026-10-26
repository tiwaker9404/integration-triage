"""Real exports come in many shapes. These are the ones the loader must survive."""

import json

import pytest

from integration_triage.diagnose import diagnose
from integration_triage.logs import load_logs, load_mapping, normalize_ts, parse_entry


def test_field_aliases_from_other_platforms():
    e = parse_entry({"requestId": "a1", "statusCode": "429", "timestamp": 1761487391000,
                     "durationMs": "120ms", "registeredUserId": "u7",
                     "headers": {"Retry-After": "30"}, "error": "Too many requests"})
    assert (e.request_id, e.status, e.latency_ms, e.user_id, e.retry_after) == ("a1", 429, 120, "u7", 30)
    assert e.ts.endswith("Z") and e.message == "Too many requests"


def test_nested_response_status_and_error_objects():
    e = parse_entry({"id": "x", "response": {"status": 404, "error": {"code": "not_found",
                     "message": "Resource not in API key scope."}}})
    assert e.status == 404 and e.error_code == "not_found" and "scope" in e.message


@pytest.mark.parametrize("raw,expected", [
    ("2026-10-20T14:03:11Z", "2026-10-20T14:03:11Z"),
    ("2026-10-20T07:03:11-07:00", "2026-10-20T14:03:11Z"),
    ("2026-10-20 14:03:11", "2026-10-20T14:03:11Z"),
    (1760968991, "2025-10-20T14:03:11Z"),
    ("1760968991000", "2025-10-20T14:03:11Z"),
])
def test_timestamps_from_mixed_sources_normalise_to_utc(raw, expected):
    assert normalize_ts(raw) == (expected, True)


def test_mixed_timezones_sort_in_true_order():
    text = "\n".join(json.dumps(r) for r in [
        {"request_id": "late", "status": 500, "ts": "2026-10-20T08:00:00-07:00"},   # 15:00Z
        {"request_id": "early", "status": 500, "ts": "2026-10-20T14:00:00Z"},
    ])
    assert [e.request_id for e in load_logs(text).entries] == ["early", "late"]


def test_json_array_wrapped_object_and_csv_all_load():
    rows = [{"request_id": f"r{i}", "status": 429, "retry_after": 30} for i in range(3)]
    assert load_logs(json.dumps(rows)).format == "json-array"
    assert load_logs(json.dumps({"data": rows})).format == "json-object"
    csv_text = "request_id,status,retry_after,ts\nr1,429,30,2026-10-20 14:00:00\nr2,429,45,2026-10-20 14:00:05\n"
    report = load_logs(csv_text)
    assert report.format == "csv" and len(report.entries) == 2
    assert diagnose(report.entries).cause_id == "rate_limited"


def test_bad_lines_are_skipped_and_reported_not_fatal():
    text = '{"request_id":"a","status":429}\nnot json\n{"request_id":"b"}\n{"status":429}\n'
    report = load_logs(text)
    assert [e.request_id for e in report.entries] == ["a", "record-4"]
    assert len(report.skipped) == 2 and "skipped 2 of 4" in report.warnings[0]


def test_unrecognised_timestamps_are_flagged():
    report = load_logs('{"request_id":"a","status":500,"ts":"last tuesday"}')
    assert report.unparsed_timestamps == 1 and "ordering" in report.warnings[0]


def test_custom_mapping_reaches_any_field():
    mapping = load_mapping('{"request_id": "meta.trace", "status": "http.code", "user_id": "who"}')
    e = parse_entry({"meta": {"trace": "t-1"}, "http": {"code": 402}, "who": "acme"}, mapping)
    assert (e.request_id, e.status, e.user_id) == ("t-1", 402, "acme")
    with pytest.raises(ValueError, match="unknown fields"):
        load_mapping('{"colour": "x"}')


def test_size_limits_fail_with_a_useful_message():
    rows = "\n".join('{"request_id":"r%d","status":200}' % i for i in range(50))
    with pytest.raises(ValueError, match="incident window"):
        load_logs(rows, max_entries=10)
    with pytest.raises(ValueError, match="MB"):
        load_logs(rows, max_bytes=100)


def test_invalid_status_is_rejected():
    for status in ("abc", 42, 700):
        with pytest.raises(ValueError):
            parse_entry({"request_id": "a", "status": status})
