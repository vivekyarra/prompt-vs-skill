"""SDK local evaluation: the emulator serves GET .../environment-document/ (post-freeze amendment, EXPERIMENT.md).

Unit tests need no browser. The `grader` tests run apps/reference/node-local-eval (`enableLocalEvaluation: true`,
`ser.` key) and a broken copy (conversion on page load) through the real grader in both modes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import urllib.error
import urllib.request

import pytest

from grader import checks as chk
from grader.mock import DOC_API_KEY, FlagsmithEmulator, hashed_percentage
from grader.tests.helpers import REPO, failed, run_grader

REF = REPO / "apps" / "reference" / "node-local-eval"
IGNORE = shutil.ignore_patterns("node_modules")


def _get(url, key=None):
    req = urllib.request.Request(url, headers={"X-Environment-Key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 (loopback)
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---- unit tests (no browser) ------------------------------------------------------------------------
def test_environment_document_needs_server_key_and_has_the_real_shape():
    emu = FlagsmithEmulator("onboarding_method", ["Join", "Join free"])
    emu.start()
    try:
        code, _ = _get(emu.url + "/api/v1/environment-document/", "GRADER_PLACEHOLDER_CLIENT_KEY")
        assert code == 401
        code, doc = _get(emu.url + "/api/v1/environment-document/", "ser.GRADER_PLACEHOLDER_SERVER_KEY_x")
        assert code == 200
        # key names of the live document (ops/dump_env_document.py)
        assert {"id", "api_key", "project", "feature_states", "identity_overrides", "name", "updated_at",
                "use_identity_composite_key_for_hashing"} <= set(doc)  # fmt: skip
        assert {"organisation", "segments", "hide_disabled_flags"} <= set(doc["project"])
        (fs,) = doc["feature_states"]
        assert fs["feature"]["name"] == "onboarding_method" and fs["feature"]["type"] == "MULTIVARIATE"
        assert fs["metadata"]["experiment"]["in_experiment"] is True
        mv = fs["multivariate_feature_state_values"]
        assert [m["multivariate_feature_option"]["value"] for m in mv] == ["Join", "Join free"]
        assert [m["multivariate_feature_option"]["key"] for m in mv] == ["variant_0", "variant_1"]
        assert sum(m["percentage_allocation"] for m in mv) == 100
        assert [r["kind"] for r in emu.records] == ["environment", "environment"]
    finally:
        emu.stop()


def test_remote_evaluation_behaviour_unchanged():
    emu = FlagsmithEmulator("f", ["Join", "Join free"])
    assert [emu.value_for("a")[0], emu.value_for("b")[0], emu.value_for("c")[0]] == ["Join free", "Join", "Join free"]
    p = emu.flag_payload("zzz")
    assert p["metadata"]["experiment"]["in_experiment"] is True and p["variant"] in ("variant_0", "variant_1")


def test_local_value_hash_is_the_engine_hash():
    # md5("<django_id>,<api_key>_<identifier>") reduced as the Flagsmith engines do
    h = int(hashlib.md5(f"1882647,{DOC_API_KEY}_user-1".encode()).hexdigest(), 16)
    assert hashed_percentage([1882647, f"{DOC_API_KEY}_user-1"]) == ((h % 9999) / 9998) * 100
    emu = FlagsmithEmulator("f", ["Join", "Join free"])
    assert {emu.local_value(f"id-{i}") for i in range(40)} == {"Join", "Join free"}  # a 50/50 split


def _records(with_document: bool):
    recs = [{"phase": "load", "kind": "events", "identifier": None, "events": [], "returned_value": None}]
    if with_document:
        recs.append({"phase": "setup", "kind": "environment", "identifier": None, "events": [], "returned_value": None})
    return recs


def test_expected_value_uses_local_value_only_after_an_environment_document_request():
    def lv(ident):
        return "X"

    flags = [{"phase": "load", "kind": "flags", "identifier": "a", "events": [], "returned_value": "R"}]
    # a flags request always wins (remote evaluation path untouched)
    assert chk.expected_value(flags + _records(True), "load", "a", lv) == "R"
    # no flags request and no environment document request: unchanged, nothing expected
    assert chk.expected_value(_records(False), "load", "a", lv) is None
    assert chk.expected_value(_records(False), "load", "a") is None
    # no flags request, document was served: the SDK's local value
    assert chk.expected_value(_records(True), "load", "a", lv) == "X"
    assert chk.expected_value(_records(True), "load", "a") is None


# ---- grader self-tests --------------------------------------------------------------------------------
def _broken_local_eval(tmp_path, bid):
    spec = importlib.util.spec_from_file_location("make_broken", REPO / "apps" / "broken" / "make_broken.py")
    mb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mb)
    dest = tmp_path / f"broken-local-eval-{bid}"
    shutil.copytree(REF, dest, ignore=IGNORE)
    getattr(mb, bid.lower())("node", dest)  # the same patch the other stacks' broken variants get
    return dest


@pytest.mark.grader
@pytest.mark.parametrize("mode", ["emulator", "proxy"])
def test_local_evaluation_reference_passes_everything(mode, tmp_path):
    res = run_grader(REF, "node", tmp_path / "r.json", mode)
    assert failed(res, include_c7=True) == set(), {c: v["reason"] for c, v in res["checks"].items() if v["reason"]}
    assert res["passed"] is True
    # proof that the SDK evaluated locally: it fetched the document and never asked the identities endpoint
    assert res["local_evaluation"]["environment_document_requests"] >= 1
    assert all(c["flags"] == 0 for c in res["request_counts"].values()), res["request_counts"]
    assert res["identities"]["v1_load"] == res["identities"]["v1_reload"] != res["identities"]["v2"]
    if mode == "proxy":
        assert {e["host"] for e in res["events_observed"]} == {"events.api.flagsmith.com"}


# Each broken copy must fail exactly its check under local evaluation (B5 also fails C4: the identity is
# regenerated per request, so the click request carries a new one; same as the other server stacks).
# (bid, failed checks, check whose reason is inspected, word in that reason, mode)
LOCAL_BROKEN = [
    ("B3", {"C3"}, "C3", "during page load", "emulator"),
    ("B3", {"C3"}, "C3", "during page load", "proxy"),
    ("B4", {"C4"}, "C4", "differs from exposure identity", "emulator"),
    ("B5", {"C4", "C5"}, "C5", "changed after reload", "emulator"),
    ("B6", {"C6"}, "C6", "Flagsmith returned", "emulator"),
    ("B6", {"C6"}, "C6", "Flagsmith returned", "proxy"),
]


@pytest.mark.grader
@pytest.mark.parametrize(("bid", "expect", "which", "word", "mode"), LOCAL_BROKEN)
def test_local_evaluation_broken_copy_fails_its_check(bid, expect, which, word, mode, tmp_path):
    res = run_grader(_broken_local_eval(tmp_path, bid), "node", tmp_path / "r.json", mode)
    assert failed(res, include_c7=True) == expect, {c: v["reason"] for c, v in res["checks"].items() if v["reason"]}
    assert word in (res["checks"][which]["reason"] or ""), res["checks"][which]
    assert res["passed"] is False
    assert res["local_evaluation"]["environment_document_requests"] >= 1
