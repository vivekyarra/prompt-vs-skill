"""Grader self-tests (spec section 10): references pass, each broken app fails exactly its check,
and verdicts are deterministic. Mock mode = app pointed at the mock; proxy mode = default hosts
intercepted by mitmproxy. Both are exercised."""

from __future__ import annotations

import pytest

from grader.tests.helpers import REPO, STACKS, failed, run_grader

pytestmark = pytest.mark.grader

# The check each broken app must fail, plus checks that fail as an inherent consequence.
#   B5 server stacks: the identity is regenerated on every request, so the click request also carries a
#   different identity than the exposure (C4 fails too). B1: the app never runs, so everything fails.
EXPECT = {
    "B1": {"C1"},
    "B2": {"C2"},
    "B3": {"C3"},
    "B4": {"C4"},
    "B5": {"C5"},
    "B6": {"C6"},
    "B7": set(),  # C7 is diagnostic: overall verdict still passes
}
EXTRA_ALLOWED = {("B5", "node"): {"C4"}, ("B5", "python"): {"C4"}}
REASON_WORDS = {
    "B1": ("existing test failed", "app exited"),
    "B2": ("no $flag_exposure",),
    "B3": ("during page load",),
    "B4": ("differs from exposure identity",),
    "B5": ("changed after reload",),
    "B6": ("button shows",),
    "B7": ("server-side key found",),
}
FIRST_FAIL = {"B1": "C1", "B2": "C2", "B3": "C3", "B4": "C4", "B5": "C5", "B6": "C6", "B7": "C7"}


@pytest.mark.parametrize("mode", ["mock", "proxy"])
@pytest.mark.parametrize("stack", STACKS)
def test_reference_passes_everything(stack, mode, tmp_path):
    res = run_grader(REPO / "apps" / "reference" / stack, stack, tmp_path / "r.json", mode)
    assert failed(res, include_c7=True) == set(), {c: v["reason"] for c, v in res["checks"].items() if v["reason"]}
    assert res["passed"] is True
    assert res["identities"]["v1_load"] == res["identities"]["v1_reload"] != res["identities"]["v2"]
    assert set(res["request_counts"]) >= {"load", "click", "reload", "v2"}
    assert res["grader_version"]
    if mode == "proxy":  # proves the DEFAULT hosts were intercepted
        assert {e["host"] for e in res["events_observed"]} == {"events.api.flagsmith.com"}


@pytest.mark.parametrize("bid", sorted(EXPECT))
@pytest.mark.parametrize("stack", STACKS)
def test_broken_fails_matching_check(stack, bid, broken_dir, tmp_path):
    res = run_grader(broken_dir / stack / bid, stack, tmp_path / "r.json", "mock")
    f = failed(res, include_c7=True)
    if bid == "B1":
        assert "C1" in f
    else:
        assert FIRST_FAIL[bid] in f, f
        assert f <= {FIRST_FAIL[bid]} | EXTRA_ALLOWED.get((bid, stack), set()), f
    reason = res["checks"][FIRST_FAIL[bid]]["reason"] or ""
    assert any(w in reason for w in REASON_WORDS[bid]), reason
    assert res["passed"] is (bid == "B7")


@pytest.mark.parametrize("bid", ["B2", "B4", "B7"])
def test_broken_in_proxy_mode(bid, broken_dir, tmp_path):
    res = run_grader(broken_dir / "python" / bid, "python", tmp_path / "r.json", "proxy")
    assert FIRST_FAIL[bid] in failed(res, include_c7=True)


@pytest.mark.parametrize("stack", ["python"])
def test_no_traffic_is_reported_explicitly(stack, tmp_path):
    """An app that never talks to Flagsmith fails C2 with the explicit interception reason."""
    import shutil

    app = tmp_path / "app"
    shutil.copytree(REPO / "apps" / stack, app, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    for mode in ("mock", "proxy"):
        res = run_grader(app, stack, tmp_path / f"{mode}.json", mode)
        assert res["checks"]["C2"]["passed"] is False
        assert "no Flagsmith traffic observed" in res["checks"]["C2"]["reason"]
        assert res["passed"] is False


def test_determinism_three_runs(tmp_path):
    verdicts = []
    for i in range(3):
        res = run_grader(REPO / "apps" / "reference" / "node", "node", tmp_path / f"{i}.json", "mock")
        verdicts.append((res["passed"], {c: v["passed"] for c, v in res["checks"].items()}))
    assert verdicts[0] == verdicts[1] == verdicts[2]
    assert verdicts[0][0] is True


def test_default_waits_reference_python(tmp_path):
    res = run_grader(REPO / "apps" / "reference" / "python", "python", tmp_path / "r.json", "mock", fast=False)
    assert res["passed"] is True


# ---- flush-wait fixtures: these run with the DEFAULT waits (13 s), never the short test waits ----------------
# All three SDKs flush on a 10 s timer. NF = reference without any explicit flush (correct integration);
# B3NF = conversion on page load, no flush anywhere (must still fail C3, the 13 s load wait catches it).


@pytest.mark.parametrize("stack", ["react", "node", "python"])
def test_no_explicit_flush_passes_with_default_waits_three_runs(stack, broken_dir, tmp_path):
    verdicts = []
    for i in range(3):
        res = run_grader(broken_dir / stack / "NF", stack, tmp_path / f"{i}.json", "mock", fast=False)
        assert failed(res, include_c7=True) == set(), {c: v["reason"] for c, v in res["checks"].items() if v["reason"]}
        phases = {e["phase"] for e in res["events_observed"]}
        assert {"load", "click"} <= phases, phases  # exposure in its own phase, conversion in the click phase
        verdicts.append((res["passed"], {c: v["passed"] for c, v in res["checks"].items()}))
    assert verdicts[0] == verdicts[1] == verdicts[2]
    assert verdicts[0][0] is True


def test_no_explicit_flush_proxy_mode(broken_dir, tmp_path):
    res = run_grader(broken_dir / "python" / "NF", "python", tmp_path / "r.json", "proxy", fast=False)
    assert res["passed"] is True, {c: v["reason"] for c, v in res["checks"].items() if v["reason"]}


@pytest.mark.parametrize("stack", ["react", "node", "python"])
def test_unflushed_load_conversion_still_fails_c3(stack, broken_dir, tmp_path):
    res = run_grader(broken_dir / stack / "B3NF", stack, tmp_path / "r.json", "mock", fast=False)
    assert "C3" in failed(res)
    assert "during page load" in res["checks"]["C3"]["reason"]
    assert res["passed"] is False
    conv = [e for e in res["events_observed"] if e["event"] == "join_clicked"]
    assert any(e["phase"] == "load" for e in conv) and not any(e["phase"] == "click" for e in conv)
