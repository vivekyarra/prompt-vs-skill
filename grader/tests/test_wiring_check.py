"""Tests for the generic wiring check: --click-selector / --event / --variant-values / --stack custom /
--start-cmd / --report on the custom-signup fixture (button #signup, event signup_clicked)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from grader import report, stacks
from grader.mock import MockFlagsmith
from grader.tests.helpers import REPO, failed

FIXTURE = REPO / "apps" / "reference" / "custom-signup"
FLAG = "signup_button_text"
VALUES = "Sign up,Create account"
IGNORE = shutil.ignore_patterns("node_modules")


def grade(app_dir, out, *extra, stack="node", mode="mock") -> tuple[dict, subprocess.CompletedProcess]:
    cmd = [
        sys.executable, "-m", "grader", "--app-dir", str(app_dir), "--stack", stack, "--flag", FLAG,
        "--event", "signup_clicked", "--variant-values", VALUES, "--out", str(out), "--mode", mode,
        "--load-wait", "1", "--click-wait", "2", *extra,
    ]  # fmt: skip
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=900, check=False)
    return json.loads(out.read_text()), proc


def broken_copy(tmp_path):
    dest = tmp_path / "broken"
    shutil.copytree(FIXTURE, dest, ignore=IGNORE)
    app = dest / "app.js"
    text = app.read_text()
    old = "      await flagsmith.flushEvents() // send the exposure now, not on the timer\n"
    assert old in text
    app.write_text(text.replace(old, "      flagsmith.trackEvent('signup_clicked', { identifier: req.vid })\n" + old))
    return dest


# ---- unit tests (no browser) --------------------------------------------------------------------
def test_mock_follows_variant_values_last_value_first():
    m = MockFlagsmith(FLAG, ["Sign up", "Create account"])
    assert m.value_for("a")[0] == "Create account"
    assert m.value_for("b")[0] == "Sign up"
    d = MockFlagsmith("f", ["Join", "Join free"])  # default path unchanged
    assert [d.value_for("a")[0], d.value_for("b")[0]] == ["Join free", "Join"]


def test_report_lists_hints_for_failed_checks_only():
    checks = {c: {"passed": True, "reason": None} for c in ("C1", "C2", "C3")}
    checks["C3"] = {"passed": False, "reason": "x was sent during page load"}
    res = {"checks": checks, "passed": False, "hints": report.hints_for(checks)}
    text = report.format_report(res)
    assert list(res["hints"]) == ["C3"]
    assert "FIX HINT: send the conversion from the click handler" in text
    assert text.count("FIX HINT") == 1
    assert "OVERALL: FAIL" in text


# ---- end to end ---------------------------------------------------------------------------------
@pytest.mark.grader
@pytest.mark.parametrize("mode", ["mock", "proxy"])
def test_custom_fixture_passes_with_new_flags(mode, tmp_path):
    res, proc = grade(FIXTURE, tmp_path / "r.json", "--click-selector", "#signup", mode=mode)
    assert failed(res, include_c7=True) == set(), {c: v["reason"] for c, v in res["checks"].items() if v["reason"]}
    assert res["passed"] and proc.returncode == 0
    assert {b for b in res["button_text"].values()} == {"Sign up", "Create account"}
    assert res["hints"] == {}
    assert {e["event"] for e in res["events_observed"] if e["phase"] == "click"} >= {"signup_clicked"}


@pytest.mark.grader
def test_custom_fixture_conversion_on_load_fails_c3_with_hint(tmp_path):
    res, proc = grade(broken_copy(tmp_path), tmp_path / "r.json", "--click-selector", "#signup", "--report")
    assert failed(res) == {"C3"}
    assert proc.returncode == 1
    assert "during page load" in res["checks"]["C3"]["reason"]
    assert set(res["hints"]) == {"C3"}
    assert "FIX HINT: send the conversion from the click handler, not on load" in proc.stdout
    assert "OVERALL: FAIL" in proc.stdout


@pytest.mark.grader
def test_wrong_selector_fails_c1_naming_the_selector(tmp_path):
    res, proc = grade(FIXTURE, tmp_path / "r.json", "--click-selector", "#nope")
    assert proc.returncode == 1
    assert "#nope" in res["checks"]["C1"]["reason"]


@pytest.mark.grader
def test_stack_custom_with_start_cmd_and_url(tmp_path):
    work = tmp_path / "app"
    shutil.copytree(FIXTURE, work, ignore=IGNORE)
    subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=work, check=True, capture_output=True)  # user installs first
    port = stacks.free_port()
    res, proc = grade(
        work, tmp_path / "r.json", "--click-selector", "#signup", "--start-cmd", "npm start",
        "--url", f"http://127.0.0.1:{port}/?utm=docs", "--port", str(port), stack="custom", mode="proxy",
    )  # fmt: skip
    assert failed(res, include_c7=True) == set(), {c: v["reason"] for c, v in res["checks"].items() if v["reason"]}
    assert "no test step for the custom stack" in res["checks"]["C1"]["detail"]
    assert proc.returncode == 0


def test_stack_custom_requires_start_cmd(tmp_path):
    cmd = [sys.executable, "-m", "grader", "--app-dir", str(FIXTURE), "--stack", "custom", "--flag", FLAG,
           "--out", str(tmp_path / "r.json")]  # fmt: skip
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 2
