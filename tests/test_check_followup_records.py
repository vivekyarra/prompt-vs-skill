"""scripts/check_followup_records.py on scripted records (never real results)."""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import check_followup_records as c  # noqa: E402


def rec(i, variant, **kw):
    r = dict(c.EXPECTED, trial_id=f"trial-1-{i}", variant=variant, prompt_sha256="p", brief_sha256="b", skill_sha="s",
             grader_sha="g", repo_sha="r", agent_version="1.19.6", runner_error=False, limit_hit="none", passed=True,
             events_sent=["integration_verified"], skill_loaded=variant == "skill", cost_usd=0.1, dry_run=False,
             scripted_agent=False)  # fmt: skip
    r.update(kw)
    return r


PRIMARY = [{"trial_id": "trial-0-1", "prompt_sha256": "p", "brief_sha256": "b"}]


def run(rows, expect=None, cap=None):
    return c.check(rows, PRIMARY, {"trial-0-1"}, expect, cap)


def batch(n=10):
    return [rec(i, "prompt" if i % 2 else "skill") for i in range(n)]


def test_clean_batch_passes_and_prints_no_pass_rate():
    info, warn, fail = run(batch(), expect=10, cap=20)
    assert not fail and not warn
    text = "\n".join(info)
    assert "records: 10 (prompt 5, skill 5" in text and "projected total at 110 trials $11.00" in text
    assert "pass" not in text.lower()


def test_each_misconfiguration_fails():
    cases = {
        "stage": dict(stage="primary"), "skill_dir": dict(skill_dir="skill/flagsmith-ab-test"),
        "environment": dict(environment="development"), "assignment": dict(assignment="local"),
        "model": dict(model="other"), "max_turns": dict(max_turns=60), "prompt_sha256": dict(prompt_sha256="x"),
        "grader_sha": dict(grader_sha="g2"), "dry-run": dict(dry_run=True), "already present": dict(trial_id="trial-0-1"),
        "contaminated": dict(variant="prompt", skill_loaded=True), "without a sent": dict(events_sent=[]),
    }  # fmt: skip
    for needle, change in cases.items():
        rows = batch()
        rows[0] = rec(0, **{"variant": "skill", **change})
        fail = run(rows)[2]
        assert any(needle in f for f in fail), (needle, fail)


def test_counts_cost_and_runner_errors():
    assert any("expected 110 records" in f for f in run(batch(), expect=110)[2])
    assert any("more than the declared 110" in f for f in run(batch(112))[2])
    assert any("over the cap" in f for f in run(batch(), cap=10.99)[2]) and not run(batch(), cap=11.01)[2]
    rows = batch(20)
    rows[0]["runner_error"] = True
    assert not run(rows)[2]  # 1/20 = 5% is not over the limit
    rows[1]["runner_error"] = True
    assert any("over the 5% limit" in f for f in run(rows)[2])
    assert any("not reaching the agent" in f for f in run([rec(i, "skill", skill_loaded=False) for i in range(4)]
                                                           + [rec(9, "prompt")])[2])  # fmt: skip
    skewed = [rec(i, "skill") for i in range(8)] + [rec(8, "prompt"), rec(9, "prompt")]
    info, warn, fail = run(skewed)
    assert any("outside 45%-55%" in w for w in warn) and not fail  # a small batch may be uneven
    assert run([], None, None)[2] == ["no records"]


def test_cli(tmp_path, capsys):
    f = tmp_path / "followup.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in batch()))
    p = tmp_path / "primary.jsonl"
    p.write_text(json.dumps(PRIMARY[0]) + "\n")
    args = [str(f), "--primary", str(p), "--replication", str(tmp_path / "none.jsonl")]
    assert c.main([*args, "--expect", "10"]) == 0
    assert "FOLLOW-UP RECORDS: OK" in capsys.readouterr().out
    assert c.main([*args, "--expect", "11"]) == 1
    assert "FOLLOW-UP RECORDS: FAIL" in capsys.readouterr().out
