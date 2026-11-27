"""Unit tests. All data here is synthetic and generated inside the tests; never real results."""

import json

from analysis import analyze, collect, crosscheck


def rec(i, variant, passed=True, over=False, stack="react", runner_error=False, failed_checks=()):
    checks = {c: c not in failed_checks for c in analyze.ALL_CHECKS}
    return {
        "trial_id": f"t-{variant}-{i}", "environment": "production", "variant": variant, "stack": stack, "passed": passed,
        "over_budget": over, "runner_error": runner_error, "turns": 10, "input_tokens": 100,
        "output_tokens": 50, "cost_usd": 0.5, "duration_s": 60, "checks": checks,
        "events_sent": (["integration_verified"] if passed else []) + (["over_budget"] if over else []),
    }


def make(variant, n, n_pass, n_over=0, start=0):
    return [rec(start + i, variant, passed=i < n_pass, over=i < n_over) for i in range(n)]


def test_chi_square_balanced_and_skewed():
    chi2, p = analyze.srm_chi_square(50, 50)
    assert chi2 == 0 and p == 1.0
    chi2, p = analyze.srm_chi_square(70, 30)
    assert abs(chi2 - 16.0) < 1e-9 and p < 0.001


def test_srm_band_and_flag():
    assert not analyze.srm_status(50, 50)["flagged"]
    assert not analyze.srm_status(46, 54)["flagged"]
    assert analyze.srm_status(40, 60)["flagged"]
    assert analyze.srm_status(0, 0)["flagged"] is False


def test_beta_binomial_clear_winner_and_symmetry():
    r = analyze.beta_binomial_diff(10, 100, 60, 100, seed=3, samples=20000)
    assert r["p_b_better"] > 0.99 and r["ci_low"] > 0
    r2 = analyze.beta_binomial_diff(60, 100, 10, 100, seed=3, samples=20000)
    assert r2["p_b_better"] < 0.01 and r2["ci_high"] < 0


def test_decision_ship_skill():
    primary = {"p_b_better": 0.99, "ci_low": 0.1, "ci_high": 0.4, "mean_diff": 0.25}
    guard = {"p_b_better": 0.5, "ci_low": -0.05, "ci_high": 0.05, "mean_diff": 0}
    d = analyze.decide(primary, guard, (100, 100), (0.3, 0.55))
    assert d["outcome"] == "ship" and d["winner"] == "skill"


def test_decision_ship_prompt():
    primary = {"p_b_better": 0.01, "ci_low": -0.4, "ci_high": -0.1, "mean_diff": -0.25}
    guard = {"p_b_better": 0.5, "ci_low": -0.05, "ci_high": 0.05, "mean_diff": 0}
    assert analyze.decide(primary, guard, (100, 100), (0.5, 0.2))["winner"] == "prompt"


def test_decision_win_prob_just_below_threshold():
    primary = {"p_b_better": 0.949, "ci_low": 0.01, "ci_high": 0.3, "mean_diff": 0.1}
    guard = {"p_b_better": 0.5, "ci_low": -0.05, "ci_high": 0.05, "mean_diff": 0}
    d = analyze.decide(primary, guard, (100, 100), (0.3, 0.4))
    assert d["outcome"] == "inconclusive" and d["extra"] is not None


def test_decision_ci_includes_zero_blocks_even_with_high_win_prob():
    primary = {"p_b_better": 0.96, "ci_low": -0.001, "ci_high": 0.3, "mean_diff": 0.1}
    guard = {"p_b_better": 0.5, "ci_low": -0.05, "ci_high": 0.05, "mean_diff": 0}
    d = analyze.decide(primary, guard, (100, 100), (0.3, 0.4))
    assert d["outcome"] == "inconclusive"
    assert any("includes zero" in r for r in d["reasons"])


def test_decision_guardrail_worse_blocks_skill_but_not_prompt_win():
    primary = {"p_b_better": 0.99, "ci_low": 0.1, "ci_high": 0.4, "mean_diff": 0.25}
    worse_for_skill = {"p_b_better": 0.99, "ci_low": 0.05, "ci_high": 0.3, "mean_diff": 0.15}
    d = analyze.decide(primary, worse_for_skill, (100, 100), (0.3, 0.55))
    assert d["outcome"] == "inconclusive"
    # skill uses MORE budget; if prompt is the winner this is not a guardrail failure for prompt
    primary_prompt = {"p_b_better": 0.01, "ci_low": -0.4, "ci_high": -0.1, "mean_diff": -0.25}
    assert analyze.decide(primary_prompt, worse_for_skill, (100, 100), (0.55, 0.3))["outcome"] == "ship"


def test_decision_zero_trials_and_zero_difference():
    p = {"p_b_better": 0.5, "ci_low": -0.1, "ci_high": 0.1, "mean_diff": 0}
    assert analyze.decide(p, p, (0, 10), (0, 0))["outcome"] == "no data"
    d = analyze.decide(p, p, (10, 10), (0.5, 0.5))
    assert d["outcome"] == "inconclusive" and d["extra"] is None


def test_extra_trials_scales_with_small_delta():
    small = analyze.extra_trials_needed(0.5, 0.55, 50)
    large = analyze.extra_trials_needed(0.5, 0.7, 50)
    assert small > large >= 0


def test_no_data_writes_no_data_yet(tmp_path):
    out = tmp_path / "RESULTS.md"
    assert analyze.main(["--trials", str(tmp_path / "missing.jsonl"), "--out", str(out)]) == 0
    assert "No data yet" in out.read_text()
    (tmp_path / "empty.jsonl").write_text("")
    analyze.main(["--trials", str(tmp_path / "empty.jsonl"), "--out", str(out)])
    assert "No data yet" in out.read_text()


def test_full_report_sections_and_runner_error_exclusion(tmp_path):
    trials = make("prompt", 40, 10, 2) + make("skill", 40, 30, 2)
    trials.append(rec(900, "skill", passed=False, runner_error=True))
    trials.append(rec(901, "prompt", passed=False, failed_checks=("C3", "C7")))
    f = tmp_path / "t.jsonl"
    f.write_text("\n".join(json.dumps(t) for t in trials) + "\n" + json.dumps(trials[0]) + "\n")
    out = tmp_path / "R.md"
    analyze.main(["--trials", str(f), "--out", str(out)])
    text = out.read_text()
    for h in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "## 7.", "## 8.", "EXPLORATORY",
              "NOT Flagsmith's statistics", "TBD - read from Flagsmith dashboard"):
        assert h in text
    assert "Runner error rate: 1/82" in text
    assert "prompt | 41 | 10" in text  # duplicate dropped, runner error excluded from skill n
    assert "skill | 40 | 30" in text


def test_treatment_fidelity_block(tmp_path):
    base = make("prompt", 20, 5) + make("skill", 20, 15)
    f0 = tmp_path / "a.jsonl"
    f0.write_text("\n".join(json.dumps(t) for t in base) + "\n")
    o0 = tmp_path / "A.md"
    analyze.main(["--trials", str(f0), "--out", str(o0)])
    t0 = o0.read_text()
    assert "Treatment fidelity" in t0 and "| prompt | unknown |" in t0 and "| skill | unknown |" in t0
    for i, t in enumerate(base):
        t["skill_loaded"] = (t["variant"] == "skill" and i % 2 == 0) or i == 0
        if t["variant"] == "skill":
            t["flag_created_during_trial"] = True
    f1 = tmp_path / "b.jsonl"
    f1.write_text("\n".join(json.dumps(t) for t in base) + "\n")
    o1 = tmp_path / "B.md"
    analyze.main(["--trials", str(f1), "--out", str(o1)])
    t1 = o1.read_text()
    assert "| prompt | 1/20 (5.0%) |" in t1 and "| skill | 10/20 (50.0%) |" in t1
    assert "| skill | 20/20 (100.0%) |" in t1 and "EXPLORATORY" in t1
    assert "P(skill > prompt)" in t1


def test_flagsmith_json_rendered(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text("\n".join(json.dumps(t) for t in make("prompt", 5, 2) + make("skill", 5, 3)))
    fs = tmp_path / "fs.json"
    fs.write_text(json.dumps({"win_probability": "SYNTHETIC", "read_at_utc": "2000-01-01T00:00Z"}))
    out = tmp_path / "R.md"
    analyze.main(["--trials", str(f), "--out", str(out), "--flagsmith-json", str(fs)])
    assert "SYNTHETIC" in out.read_text()


def test_crosscheck_match_and_diff():
    trials = make("prompt", 20, 5) + make("skill", 20, 8)
    ours = crosscheck.our_counts(trials)
    assert ours["exposures"] == {"prompt": 20, "skill": 20}
    theirs = {"exposures": {"prompt": 20, "skill": 20},
              "events": {"integration_verified": {"prompt": 5, "skill": 8},
                         "over_budget": {"prompt": 0, "skill": 0}}}
    assert all(r["ok"] for r in crosscheck.compare(ours, theirs))
    theirs["events"]["integration_verified"]["skill"] = 3
    rows = crosscheck.compare(ours, theirs)
    assert not all(r["ok"] for r in rows)
    assert not crosscheck.compare(ours, {})[0]["ok"]


def test_collect_dedupes(tmp_path):
    art = tmp_path / "art"
    (art / "a").mkdir(parents=True)
    (art / "b").mkdir()
    (art / "a" / "trial.json").write_text(json.dumps({"trial_id": "x1", "variant": "skill", "environment": "production"}))
    (art / "b" / "trial.json").write_text(json.dumps({"trial_id": "x1", "variant": "skill", "environment": "production"}))
    (art / "b" / "bad.jsonl").write_text("not json")
    out = tmp_path / "data" / "trials.jsonl"
    assert collect.collect(art, out) == 1
    assert collect.collect(art, out) == 0
    assert len(out.read_text().splitlines()) == 1


def test_collect_routes_pilot_and_production(tmp_path):
    import json

    from analysis import collect as c

    art = tmp_path / "art"
    art.mkdir()
    recs = [
        {"trial_id": "a", "variant": "skill", "environment": "production", "assignment": "flagsmith"},
        {"trial_id": "b", "variant": "skill", "environment": "development", "assignment": "flagsmith"},
        {"trial_id": "c", "variant": "prompt", "environment": "production", "assignment": "local"},
        {"trial_id": "d", "variant": "prompt"},
    ]
    for r in recs:
        (art / f"{r['trial_id']}.json").write_text(json.dumps(r))
    out = tmp_path / "data" / "trials.jsonl"
    assert c.collect(art, out) == 4
    assert [json.loads(x)["trial_id"] for x in out.read_text().splitlines()] == ["a"]
    pilot = out.with_name("pilot.jsonl")
    assert sorted(json.loads(x)["trial_id"] for x in pilot.read_text().splitlines()) == ["b", "c", "d"]
    assert c.collect(art, out) == 0  # idempotent


def test_analyze_excludes_non_experiment_records():
    from analysis import analyze as a

    assert a.is_experiment_record({"environment": "production", "assignment": "flagsmith"})
    assert not a.is_experiment_record({"environment": "development", "assignment": "flagsmith"})
    assert not a.is_experiment_record({"environment": "production", "assignment": "local"})
    assert not a.is_experiment_record({"environment": "production", "dry_run": True})
    assert not a.is_experiment_record({})


def test_corrections_applied_only_when_confirmed_and_one_directional():
    from analysis import analyze as a

    trials = [
        {"trial_id": "t1", "variant": "skill", "passed": False, "checks": {"C1": False}},
        {"trial_id": "t2", "variant": "skill", "passed": True, "checks": {"C1": True}},
        {"trial_id": "t3", "variant": "prompt", "passed": False, "checks": {"C1": False}},
    ]
    corr = [
        {"trial_id": "t1", "check": "C1", "new_passed": True, "replays_passed": "3/3"},
        {"trial_id": "t3", "check": "C1", "new_passed": True, "replays_passed": "pending"},
        {"trial_id": "t2", "check": "C1", "new_passed": False, "replays_passed": "3/3"},
    ]
    new, applied = a.apply_corrections(trials, corr)
    assert [t["passed"] for t in new] == [True, True, False]
    assert len(applied) == 1 and new[0]["original_passed"] is False
    assert "as corrected" in a.corrections_section(trials, new, applied)


def test_flagged_sensitivity_section():
    from analysis import analyze as a

    ts = [
        {"trial_id": "f1", "variant": "skill", "passed": False},
        {"trial_id": "ok", "variant": "skill", "passed": True},
        {"trial_id": "p", "variant": "prompt", "passed": True},
    ]
    txt = a.flagged_section(ts, [{"trial_id": "f1", "variant": "skill", "stack": "node"}])
    assert "excluding 1 flagged" in txt and "1/2" in txt and "1/1" in txt
    assert a.flagged_section(ts, [{"trial_id": "none"}]) == ""


def test_flagsmith_snapshot_conversion():
    from analysis import analyze as a

    snap = {"results": {"as_of": "T", "results": {"as_of": "T", "payload": {"metrics": [
        {"metric_id": 1, "variants": {"control": {"n": 10, "sum": 10.0}, "skill": {"n": 10, "sum": 8.0}},
         "inference": {"skill": {"lift": -0.2, "ci_low": -0.4, "ci_high": -0.01, "chance_to_win": 0.01}}},
        {"metric_id": 2, "variants": {"control": {"n": 10, "sum": 0.0}, "skill": {"n": 10, "sum": 1.0}}},
    ]}}}}  # fmt: skip
    out = a.fs_from_snapshot(snap)
    assert out["exposures"] == {"prompt": 10, "skill": 10}
    assert out["integration_verified_rate"]["skill"].startswith("8/10")
    assert "1/10" in out["guardrail_over_budget"]["skill"]
    assert "0.010000%" not in out["win_probability"] and "skill 1.0" in out["win_probability"]
