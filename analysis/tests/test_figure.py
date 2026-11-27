"""Figure tests. All data is built inside the tests; never real results."""

import json
import xml.etree.ElementTree as ET

from analysis import analyze, figure
from analysis.tests.test_analysis import make, rec


def _texts(svg: str) -> str:
    root = ET.fromstring(svg)
    return " ".join("".join(e.itertext()) for e in root.iter() if e.tag.endswith("text"))


def _trials():
    t = make("prompt", 40, 20, n_over=3) + make("skill", 40, 32, n_over=2)
    t += [rec(100 + i, "skill", passed=False, failed_checks=("C2", "C5")) for i in range(4)]
    t += [rec(200, "prompt", passed=False, runner_error=True)]
    return t


def test_no_data_renders_neutral_svgs():
    assert analyze.figure_stats([], 1) is None
    for fn in (figure.results_svg, figure.failures_svg):
        svg = fn(None, "2026-01-01 00:00 UTC", "primary")
        ET.fromstring(svg)
        assert "No data yet" in svg and "<title" in svg and "<desc" in svg
        assert "generated from data/trials.jsonl at 2026-01-01 00:00 UTC; stage primary" in svg


def test_numbers_in_svg_match_analysis():
    trials = _trials()
    seed = 7
    st = analyze.figure_stats(trials, seed)
    s = analyze.summarise(trials)
    p, k = s["variants"]["prompt"], s["variants"]["skill"]
    svg = figure.results_svg(st, "T", "primary")
    text = _texts(svg)
    ET.fromstring(svg)
    # independent recomputation through the analysis functions
    diff = analyze.beta_binomial_diff(p["passed"], p["n"], k["passed"], k["n"], seed)
    lo, hi = analyze.beta_interval(p["passed"], p["n"], seed)
    assert f"n = {p['n']}" in text and f"n = {k['n']}" in text
    assert analyze.fmt_pct(p["passed"] / p["n"]) in text and f"{p['passed']}/{p['n']}" in text
    assert f"{lo:.1%} to {hi:.1%}" in text
    assert f"[{diff['ci_low']:+.3f}, {diff['ci_high']:+.3f}]" in text
    assert f"Mean {diff['mean_diff']:+.3f}" in text
    assert f"P(skill > prompt) = {diff['p_b_better']:.1%}" in text
    assert "Own-log verdict:" in text and "generated from data/trials.jsonl at T; stage primary" in text
    assert "<title" in svg and "<desc" in svg and "prefers-color-scheme: dark" in svg
    assert p["runner_errors"] == 1 and p["n"] == 40  # runner error excluded from n


def test_failures_svg_numbers_and_labels():
    trials = _trials()
    st = analyze.figure_stats(trials, 1)
    k = analyze.summarise(trials)["variants"]["skill"]
    svg = figure.failures_svg(st, "T", "primary")
    text = _texts(svg)
    ET.fromstring(svg)
    for c in analyze.PRIMARY_CHECKS:
        assert c in text
    assert f"skill n = {k['n']}" in text
    assert f"{k['check_fail']['C2']}/{k['n']} ({k['check_fail']['C2'] / k['n']:.1%})" in text


def test_one_empty_arm_does_not_crash():
    st = analyze.figure_stats(make("prompt", 5, 3), 1)
    text = _texts(figure.results_svg(st, "T", "primary"))
    assert "no analysable trials" in text and "Not computable" in text
    ET.fromstring(figure.failures_svg(st, "T", "primary"))


def test_cli_writes_figures_and_embeds_relative_links(tmp_path):
    trials = tmp_path / "t.jsonl"
    rows = _trials()
    trials.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = tmp_path / "docs" / "R.md"
    out.parent.mkdir()
    figs = tmp_path / "docs" / "figs"
    analyze.main(["--trials", str(trials), "--out", str(out), "--figures-dir", str(figs),
                  "--corrections", str(tmp_path / "none"), "--flagged", str(tmp_path / "none")])  # fmt: skip
    assert (figs / "results.svg").exists() and (figs / "failures.svg").exists()
    md = out.read_text()
    assert "(figs/results.svg)" in md and "(figs/failures.svg)" in md
    assert "stage primary" in (figs / "results.svg").read_text()


def test_cli_no_data_writes_neutral_figures(tmp_path):
    out = tmp_path / "R.md"
    figs = tmp_path / "f"
    analyze.main(["--trials", str(tmp_path / "missing.jsonl"), "--out", str(out), "--figures-dir", str(figs),
                  "--corrections", str(tmp_path / "none"), "--flagged", str(tmp_path / "none")])  # fmt: skip
    assert "No data yet" in (figs / "results.svg").read_text()
    assert "![" not in out.read_text()
