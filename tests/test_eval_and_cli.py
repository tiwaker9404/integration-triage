import json
from pathlib import Path

from integration_triage.cli import main
from integration_triage.evaluate import MAX_DROP, check, load_cases, run_eval

ROOT = Path(__file__).resolve().parents[1]


def test_cases_are_well_formed_and_cover_every_cause():
    from integration_triage.causes import CAUSES
    cases = load_cases()
    assert len({c["id"] for c in cases}) == len(cases) >= 50
    assert {c["gold"]["cause"] for c in cases} == set(CAUSES)
    assert {c["kind"] for c in cases} == {"standard", "hard", "wild"}


def test_eval_scores_every_metric():
    report = run_eval()
    assert set(report["metrics"]) == set(MAX_DROP)
    assert report["metrics"]["no_secret_leak"] == 1.0
    assert report["metrics"]["evidence_valid"] == 1.0


def test_check_blocks_zero_tolerance_drops_but_allows_small_ones():
    base = {"metrics": {m: 1.0 for m in MAX_DROP}}
    ok = {"metrics": {**base["metrics"], "cause_accuracy": 0.98}}
    bad_leak = {"metrics": {**base["metrics"], "no_secret_leak": 0.99}}
    bad_acc = {"metrics": {**base["metrics"], "cause_accuracy": 0.90}}
    assert check(base, ok)["passed"]
    assert not check(base, bad_leak)["passed"]
    assert not check(base, bad_acc)["passed"]


def test_disabling_redaction_is_caught_by_the_eval(monkeypatch):
    import integration_triage.compose as compose
    monkeypatch.setattr(compose, "redact", lambda t, keep=(): t)
    assert run_eval()["metrics"]["no_secret_leak"] < 1.0


def test_committed_baseline_still_passes(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert main(["eval", "--check"]) == 0


def test_eval_check_without_a_baseline_is_a_setup_error(tmp_path):
    assert main(["eval", "--check", "--baseline", str(tmp_path / "none.json")]) == 2


def test_diagnose_cli_end_to_end(tmp_path, capsys):
    case = next(c for c in load_cases() if c["id"] == "case19")
    logs = tmp_path / "logs.jsonl"
    logs.write_text("\n".join(json.dumps(r) for r in case["logs"]))
    assert main(["diagnose", "--logs", str(logs), "--ticket", case["ticket"]]) == 0
    out = capsys.readouterr().out
    assert "upstream_outage" in out and "page on-call: YES" in out
    assert case["gold"]["secrets"][0] not in out


def test_diagnose_cli_json_and_bad_input(tmp_path, capsys):
    logs = tmp_path / "l.jsonl"
    logs.write_text('{"request_id":"a","status":429,"retry_after":5}\n'
                    '{"request_id":"b","status":429,"retry_after":9}')
    assert main(["diagnose", "--logs", str(logs), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["cause"] == "rate_limited"
    logs.write_text("garbage")
    assert main(["diagnose", "--logs", str(logs)]) == 2


def test_runbooks_command_writes_one_file_per_cause(tmp_path):
    from integration_triage.causes import CAUSES
    assert main(["runbooks", "--out", str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("*.md"))) == len(CAUSES) + 1
