"""rollover_experiment.py against a scripted stub of the Flagsmith Admin API (no network, no credentials).

Covers the path the skill v2 follow-up needs: the old experiment is already completed (the replication was ended
with a rollout decision), so nothing is completed again and a new experiment is created and started 50/50.
"""

import runpy
import sys
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parents[1] / "ops"
sys.path.insert(0, str(OPS))
import rolllib  # noqa: E402

E = "environments/stub-env"


class StubApi:
    """Scripted stand-in for fslib.Api: one flag, two metrics, a list of experiments; records every call."""

    def __init__(self, experiments):
        self.experiments = experiments
        self.calls = []

    def results(self, path):
        if path == f"{E}/experiments/":
            return [dict(x) for x in self.experiments]
        if path.startswith("projects/1/features/?search="):
            return [{"id": 5, "name": "onboarding_method"}]
        if path == "projects/1/features/5/mv-options/":
            return [{"id": 9, "string_value": "skill", "key": "skill", "default_percentage_allocation": 0}]
        if path == f"{E}/experiment-metrics/":
            return [{"name": "integration_verified", "id": 1}, {"name": "over_budget", "id": 2}]
        if path.startswith(f"{E}/featurestates/"):
            return []
        raise AssertionError(f"unexpected list call {path}")

    def call(self, method, path, body=None, quiet=False):
        self.calls.append((method, path, body))
        if method == "POST" and path == f"{E}/experiments/":
            new = dict(body, id=77, status="created")
            self.experiments.append(new)
            return 201, new
        for x in self.experiments:
            base = f"{E}/experiments/{x['id']}/"
            if method == "POST" and path == base + "start/":
                x["status"] = "running"
                return 200, x
            if method == "POST" and path == base + "complete/":
                x["status"] = "completed"
                return 200, x
            if method == "GET" and path == base + "results/":
                return 200, {"results": {"as_of": "2026-11-27T11:02:42Z"}}
            if method == "GET" and path == base:
                return 200, x
        raise AssertionError(f"unexpected call {method} {path}")


def _run(monkeypatch, api, *args):
    monkeypatch.setattr(rolllib, "connect", lambda env_name: (api, E, "1", "stub-env"))
    monkeypatch.setattr(sys, "argv", ["rollover_experiment.py", *args])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(OPS / "rollover_experiment.py"), run_name="__main__")
    return exc.value.code


def _posts(api, suffix):
    return [c for c in api.calls if c[0] == "POST" and c[1].endswith(suffix)]


def test_completed_old_experiment_is_left_alone_and_the_followup_is_created_and_started(monkeypatch):
    api = StubApi([{"id": 42, "name": "Handoff: Replication", "status": "completed", "feature": 5}])
    code = _run(monkeypatch, api, "Production", "Handoff:_Replication", "Handoff:_Skill_v2", "--hypothesis=followup")
    assert code == 0
    assert not _posts(api, "/complete/")  # a completed experiment is never completed again
    (create,) = _posts(api, f"{E}/experiments/")
    body = create[2]
    assert body["name"] == "Handoff: Skill v2" and body["feature"] == 5
    assert body["hypothesis"] == rolllib.HYPOTHESES["followup"]
    assert body["experiment_rollout"]["rollout_percentage"] == 100
    assert body["experiment_rollout"]["feature_state_value"]["value"] == "prompt"
    assert body["experiment_rollout"]["multivariate_feature_state_values"] == [
        {"multivariate_feature_option": 9, "percentage_allocation": 50}]  # fmt: skip
    assert [c[1] for c in _posts(api, "/start/")] == [f"{E}/experiments/77/start/"]
    assert api.experiments[0]["status"] == "completed" and api.experiments[1]["status"] == "running"


def test_second_run_is_idempotent(monkeypatch):
    api = StubApi([{"id": 42, "name": "Handoff: Replication", "status": "completed", "feature": 5}])
    args = ("Production", "Handoff:_Replication", "Handoff:_Skill_v2", "--hypothesis=followup")
    assert _run(monkeypatch, api, *args) == 0
    api.calls.clear()
    assert _run(monkeypatch, api, *args) == 0
    assert not [c for c in api.calls if c[0] == "POST"]  # nothing created, started or completed twice


def test_default_hypothesis_is_the_replication_text(monkeypatch):
    api = StubApi([{"id": 42, "name": "old", "status": "running", "feature": 5}])
    assert _run(monkeypatch, api, "Development", "old", "new") == 0
    assert _posts(api, f"{E}/experiments/")[0][2]["hypothesis"] == rolllib.HYPOTHESES["replication"]
    assert rolllib.HYPOTHESES["replication"].startswith("Replication (same frozen configuration as the primary)")
    assert [c[1] for c in _posts(api, "/complete/")] == [f"{E}/experiments/42/complete/"]


def test_refuses_an_unknown_hypothesis_and_a_missing_old_experiment(monkeypatch):
    api = StubApi([])
    assert _run(monkeypatch, api, "Production", "a", "b", "--hypothesis=nope") not in (0, None)
    assert _run(monkeypatch, api, "Production", "Handoff:_Replication", "Handoff:_Skill_v2") == 1
    assert not [c for c in api.calls if c[0] == "POST"]


def test_pop_option():
    assert rolllib.pop_option(["a", "--hypothesis=followup", "--flag=x"], "hypothesis") == (["a", "--flag=x"], "followup")
    assert rolllib.pop_option(["a", "b"], "hypothesis") == (["a", "b"], None)
