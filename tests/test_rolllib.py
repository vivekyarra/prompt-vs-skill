import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
import rolllib as r  # noqa: E402


def test_resolve_name():
    assert r.resolve_name("Handoff:_Prompt_vs_Skill") == "Handoff: Prompt vs Skill"


def test_split_args():
    assert r.split_args(["Development", "a", "b", "--flag=x"]) == (["Development", "a", "b"], "x")
    assert r.split_args(["--flag", "y", "Production"]) == (["Production"], "y")
    assert r.split_args(["p"]) == (["p"], None)


def test_pick_running():
    exps = [{"id": 1, "status": "running", "feature": 5}, {"id": 2, "status": "completed", "feature": 5},
            {"id": 3, "status": "running", "feature": {"id": 5}}, {"id": 4, "status": "running", "feature": 6}]  # fmt: skip
    assert [x["id"] for x in r.pick_running(exps, 5)] == [1, 3]


def test_freshness():
    since = datetime(2026, 11, 27, 7, 0, tzinfo=timezone.utc)
    assert r.is_fresh("2026-11-27T07:01:00Z", since)
    assert not r.is_fresh("2026-11-27T06:59:00Z", since)
    assert not r.is_fresh(None, since) and not r.is_fresh("garbage", since)
    assert r.results_as_of({"results": {"as_of": "x"}}) == "x" and r.results_as_of(None) is None


def test_weights():
    detail = {"experiment_rollout": {"multivariate_feature_state_values": [
        {"multivariate_feature_option": 9, "percentage_allocation": 50}]}}  # fmt: skip
    w = r.rollout_weights(detail, {9: "skill"})
    assert w == {"skill": 50.0, "prompt": 50.0} and r.is_5050(w)
    bad = r.rollout_weights({"experiment_rollout": {"multivariate_feature_state_values": [
        {"multivariate_feature_option": {"id": 9}, "percentage_allocation": 30}]}}, {9: "skill"})  # fmt: skip
    assert not r.is_5050(bad)
    assert not r.is_5050(r.rollout_weights({}, {}))


def test_decisions():
    assert r.decision_bodies("prompt") == [{"rollout_decision": "control"}]
    opt = {"id": 7, "key": "skill", "uuid": "u-1"}
    bodies = r.decision_bodies("skill", opt)
    assert [b["rollout_variant"] for b in bodies] == [7]  # verified form: integer option id
    assert all(b["rollout_decision"] == "variant" for b in bodies)
    with pytest.raises(ValueError):
        r.decision_bodies("both")


def test_snapshot_keeps_inference_and_is_json():
    import json

    res = {"results": {"as_of": "2026-11-27T07:00:00Z", "payload": {"metrics": [{"inference": {"p": 0.9}}]}}}
    s = r.build_snapshot("Production", {"id": 1, "name": "n", "status": "running", "extra": 1}, res,
                         [{"status": "created", "total_events_received": 3, "unique_events_count": 2}],
                         datetime(2026, 11, 27, 8, 0, tzinfo=timezone.utc), True)  # fmt: skip
    t = json.loads(json.dumps(s))
    assert t["results"]["results"]["payload"]["metrics"][0]["inference"] == {"p": 0.9}
    assert t["as_of"] == "2026-11-27T07:00:00Z" and t["snapshot_utc"] == "2026-11-27T08:00:00Z"
    assert "extra" not in t["experiment"] and t["experiment"]["id"] == 1
