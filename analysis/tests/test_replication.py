"""Replication reporting. All data is scripted inside the tests; never real results."""

import json

from analysis import analyze

from .test_analysis import rec


def _stage(i, variant, stage, passed=True, **kw):
    r = rec(i, variant, passed=passed, **kw)
    r["trial_id"] = f"{stage}-{variant}-{i}"
    r["stage"] = stage
    return r


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _snap(n_p, c_p, n_s, c_s):
    return {"results": {"as_of": "T", "results": {"as_of": "T", "payload": {"metrics": [
        {"metric_id": 1, "variants": {"control": {"n": n_p, "sum": float(c_p)}, "skill": {"n": n_s, "sum": float(c_s)}},
         "inference": {"skill": {"lift": -0.1, "ci_low": -0.2, "ci_high": -0.01, "chance_to_win": 0.01}}},
        {"metric_id": 2, "variants": {"control": {"n": n_p, "sum": 0.0}, "skill": {"n": n_s, "sum": 0.0}}},
    ]}}}}  # fmt: skip


def _setup(tmp_path, rep_snap=None):
    prim = [_stage(i, "prompt", "primary") for i in range(10)] + \
           [_stage(i, "skill", "primary", passed=i < 8) for i in range(10)]  # fmt: skip
    repl = [_stage(i, "prompt", "replication", passed=i < 9) for i in range(10)] + \
           [_stage(i, "skill", "replication", passed=i < 7) for i in range(9)] + \
           [_stage(9, "skill", "replication", passed=False, runner_error=True)]  # fmt: skip
    t, r = tmp_path / "t.jsonl", tmp_path / "r.jsonl"
    _write(t, prim + repl)  # replication rows in the primary file must not leak into the primary stage
    _write(r, repl)
    f = tmp_path / "rep.json"
    f.write_text(json.dumps(rep_snap or _snap(10, 9, 10, 7)))
    return t, r, f


def _run(tmp_path, t, *extra):
    out = tmp_path / "R.md"
    analyze.main(["--trials", str(t), "--out", str(out), "--corrections", str(tmp_path / "none"),
                  "--notes", "", "--figures-dir", str(tmp_path / "fig"), *extra])  # fmt: skip
    return out.read_text()


def test_section_only_when_both_inputs_exist(tmp_path):
    t, r, f = _setup(tmp_path)
    head = "## Replication (second independent run"
    assert head not in _run(tmp_path, t)
    assert head not in _run(tmp_path, t, "--replication-trials", str(r))
    assert head not in _run(tmp_path, t, "--replication-flagsmith-json", str(f))
    assert head not in _run(tmp_path, t, "--replication-trials", str(tmp_path / "missing.jsonl"),
                            "--replication-flagsmith-json", str(f))  # fmt: skip
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert head not in _run(tmp_path, t, "--replication-trials", str(empty), "--replication-flagsmith-json", str(f))
    text = _run(tmp_path, t, "--replication-trials", str(r), "--replication-flagsmith-json", str(f))
    assert head in text and "never pooled into its decision)" in text
    for needle in ("Primary vs replication", "Pooled, secondary, not the decision: prompt 19/20, skill 15/19",
                   "Replication: cross-check of our log", "Replication: sanity checks",
                   "(replication, not the decision)", "Runner errors"):  # fmt: skip
        assert needle in text, needle
    assert "| primary | 10/10 | 8/10 |" in text and "| replication | 9/10 | 7/9 |" in text
    assert "All counts match" not in text.split(head)[0]


def test_primary_numbers_unchanged_by_replication(tmp_path):
    t, r, f = _setup(tmp_path)
    base = _run(tmp_path, t)
    text = _run(tmp_path, t, "--replication-trials", str(r), "--replication-flagsmith-json", str(f))
    cut = "\n## Replication (second independent run"
    before = text.split(cut)[0]

    def body(s):  # drop the timestamp line
        return [x for x in s.splitlines() if not x.startswith("_Generated")]

    assert body(before) == body(base)
    # primary denominators exclude the replication rows
    assert "| prompt | 10 | 10 | 100.0% |" in before and "| skill | 10 | 8 | 80.0% |" in before


def test_crosscheck_in_section_match_and_diff(tmp_path):
    t, r, f = _setup(tmp_path)
    ok = _run(tmp_path, t, "--replication-trials", str(r), "--replication-flagsmith-json", str(f))
    sect = ok.split("## Replication (second independent run")[1]
    # exposures count runner errors (skill 10), conversions are passes (7)
    assert "| skill | 10 | 10 | 7 | 7 | match |" in sect and "All counts match." in sect
    f.write_text(json.dumps(_snap(10, 9, 10, 6)))
    bad = _run(tmp_path, t, "--replication-trials", str(r), "--replication-flagsmith-json", str(f))
    assert "DIFFERENT" in bad and "Counts differ" in bad


def test_replication_sentence(tmp_path):
    t, r, f = _setup(tmp_path)
    rows = [json.loads(x) for x in r.read_text().splitlines()]
    s = analyze.replication_summary_sentence(analyze._arm_stats(rows, 1),
                                             analyze.fs_from_snapshot(_snap(10, 9, 10, 7)))  # fmt: skip
    assert s.startswith("Replication (20 trials, identical setup): prompt 9/10, skill 7/9;")
    assert "1 runner error(s) excluded" in s and "prompt 9/10 and skill 7/10" in s
    assert s.endswith(".") and "\n" not in s and s.count("Replication (") == 1


def test_print_replication_sentence_cli(tmp_path, capsys):
    t, r, f = _setup(tmp_path)
    out = tmp_path / "R.md"
    code = analyze.main(["--trials", str(t), "--out", str(out), "--replication-trials", str(r),
                         "--replication-flagsmith-json", str(f), "--print-replication-sentence"])  # fmt: skip
    assert code == 0 and not out.exists()
    assert capsys.readouterr().out.startswith("Replication (20 trials, identical setup)")
    assert analyze.main(["--print-replication-sentence"]) == 1
