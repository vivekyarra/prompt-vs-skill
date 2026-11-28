"""Skill v2 follow-up reporting (exploratory, never pooled). All data is scripted inside the tests; never real results."""

import json

from analysis import analyze

from .test_replication import _run, _snap, _stage, _write

HEAD = "## Follow-up: skill v2 (exploratory"
V2 = "skill/flagsmith-ab-test-v2"


def _fu(i, variant, passed=True, skill_dir=V2, **kw):
    r = _stage(i, variant, "followup", passed=passed, **kw)
    r["skill_dir"] = skill_dir
    return r


def _setup(tmp_path, followup=None, snap=None):
    prim = [_stage(i, "prompt", "primary") for i in range(10)] + \
           [_stage(i, "skill", "primary", passed=i < 8) for i in range(10)]  # fmt: skip
    repl = [_stage(i, "prompt", "replication", passed=i < 9) for i in range(10)] + \
           [_stage(i, "skill", "replication", passed=i < 7) for i in range(10)]  # fmt: skip
    fu = followup if followup is not None else (
        [_fu(i, "prompt", passed=i < 5, stack="node") for i in range(6)]
        + [_fu(i, "skill", passed=i < 4, failed_checks=() if i < 4 else ("C2", "C4")) for i in range(5)]
        + [_fu(5, "skill", passed=False, runner_error=True)])  # fmt: skip
    t, r, u = tmp_path / "t.jsonl", tmp_path / "r.jsonl", tmp_path / "u.jsonl"
    _write(t, prim + fu)  # follow-up rows in the primary file must not leak into the primary stage
    _write(r, repl)
    _write(u, fu + prim)  # primary rows in the follow-up file must not leak into the follow-up section
    rf, uf = tmp_path / "rep.json", tmp_path / "fu.json"
    rf.write_text(json.dumps(_snap(10, 9, 10, 7)))
    uf.write_text(json.dumps(snap or _snap(6, 5, 6, 4)))
    return t, r, u, rf, uf


def _body(s):  # drop the timestamp line
    return [x for x in s.splitlines() if not x.startswith("_Generated")]


def test_output_is_unchanged_without_the_followup_option(tmp_path):
    t, r, u, rf, uf = _setup(tmp_path)
    rep = ("--replication-trials", str(r), "--replication-flagsmith-json", str(rf))
    base = _run(tmp_path, t, *rep)
    assert HEAD not in base
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    for extra in (("--followup-flagsmith-json", str(uf)), ("--followup-trials", str(empty)),
                  ("--followup-trials", str(tmp_path / "missing.jsonl"), "--followup-flagsmith-json", str(uf))):  # fmt: skip
        assert _body(_run(tmp_path, t, *rep, *extra)) == _body(base)


def test_section_sits_after_the_replication_and_changes_nothing_else(tmp_path):
    t, r, u, rf, uf = _setup(tmp_path)
    rep = ("--replication-trials", str(r), "--replication-flagsmith-json", str(rf))
    base = _run(tmp_path, t, *rep)
    text = _run(tmp_path, t, *rep, "--followup-trials", str(u), "--followup-flagsmith-json", str(uf))
    before, rest = text.split("\n" + HEAD, 1)
    assert "## Replication (second independent run" in before
    # removing the follow-up section gives back the report without it, line for line
    section_lines = len(("\n" + HEAD + rest).splitlines())
    start = len(before.splitlines())
    lines = text.splitlines()
    assert _body("\n".join(lines[:start] + lines[start + section_lines:])) == _body(base)
    # nothing pooled: primary and replication numbers are the ones of the report without the follow-up
    assert "| primary | 10/10 | 8/10 |" in before and "Pooled, secondary, not the decision: prompt 19/20, skill 15/20" in before


def test_section_content(tmp_path):
    t, r, u, rf, uf = _setup(tmp_path)
    text = _run(tmp_path, t, "--followup-trials", str(u), "--followup-flagsmith-json", str(uf))
    sect = text.split(HEAD)[1]
    for needle in ("never pooled, no decision rule)", "**Decision rule: N/A.**", "### Follow-up: Flagsmith's numbers",
                   "| Lift | -10.0% (skill relative to prompt) |", "| Win probability |",
                   "| prompt | 6 | 0 | 6 | 5 | 83.3% | [", "| skill v2 | 6 | 1 | 5 | 4 | 80.0% | [",
                   "Difference (skill v2 - prompt), descriptive", "| skill | 6 | 6 | 4 | 4 | match |", "All counts match.",
                   f"Skill folder recorded (`skill_dir`): `{V2}`. **OK**", "Records: 12 (**NOT the declared count of 110",
                   "### Follow-up: cost and speed", "### Follow-up: where agents fail", "| C2 | 0 | 0.0% | 1 | 20.0% |",
                   "`followup-skill-4` (skill, react): C2, C4; limit hit: none.",
                   "### Follow-up: per-stack results", "| node | 5/6 (83.3%) | 0/0 (n/a) |", "| react | 0/0 (n/a) | 4/5 (80.0%) |",
                   "### Follow-up: treatment fidelity"):  # fmt: skip
        assert needle in sect, needle
    # exploratory: no own-log win probability and no verdict in this section
    assert "P(skill > prompt)" not in sect and "verdict" not in sect.lower() and "SHIP" not in sect


def test_wrong_skill_folder_is_called_out(tmp_path):
    rows = [_fu(i, "prompt") for i in range(3)] + [_fu(i, "skill", skill_dir="skill/flagsmith-ab-test") for i in range(3)]
    t, r, u, rf, uf = _setup(tmp_path, followup=rows, snap=_snap(3, 3, 3, 3))
    text = _run(tmp_path, t, "--followup-trials", str(u), "--followup-flagsmith-json", str(uf))
    assert "NOT only skill/flagsmith-ab-test-v2" in text


def test_section_without_a_snapshot_and_not_for_other_stages(tmp_path):
    t, r, u, rf, uf = _setup(tmp_path)
    text = _run(tmp_path, t, "--followup-trials", str(u))
    assert HEAD in text and "No Flagsmith snapshot supplied for the follow-up" in text
    assert HEAD not in _run(tmp_path, t, "--followup-trials", str(u), "--stage", "replication")
    assert HEAD not in _run(tmp_path, t, "--followup-trials", str(u), "--include-all")


def test_followup_sentence_cli(tmp_path, capsys):
    t, r, u, rf, uf = _setup(tmp_path)
    out = tmp_path / "R.md"
    code = analyze.main(["--trials", str(t), "--out", str(out), "--followup-trials", str(u),
                         "--followup-flagsmith-json", str(uf), "--print-followup-sentence"])  # fmt: skip
    s = capsys.readouterr().out.strip()
    assert code == 0 and not out.exists()
    assert s.startswith("Follow-up, exploratory (12 trials, skill v2 against the official prompt, never pooled): "
                        "prompt 5/6, skill v2 4/5;")  # fmt: skip
    assert "1 runner error(s) excluded" in s and "prompt 5/6 and skill v2 4/6" in s and s.endswith(".")
    assert analyze.main(["--print-followup-sentence"]) == 1
    # every count-like token of the sentence is in the RESULTS section (scripts/check_readme_numbers.py relies on it)
    import re

    token = re.compile(r"\b\d+ of \d+\b|\b\d+/\d+\b|[-+]\d+\.\d+%?|\b\d+\.\d+%")
    sect = _run(tmp_path, t, "--followup-trials", str(u), "--followup-flagsmith-json", str(uf)).split(HEAD)[1]
    assert token.findall(s) and all(tok in sect for tok in token.findall(s)), token.findall(s)
