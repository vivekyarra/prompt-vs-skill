"""The trials.yml guard step: a follow-up dispatch is stage=followup + skill v2 + Flagsmith assignment, or it is refused
before any trial job starts. The step's shell script is run here as written in the workflow (no network)."""

import pathlib
import subprocess

import pytest
import yaml

WF = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "trials.yml"
V1, V2 = "skill/flagsmith-ab-test", "skill/flagsmith-ab-test-v2"


def _guard():
    job = yaml.safe_load(WF.read_text())["jobs"]["prepare"]
    return next(s for s in job["steps"] if s.get("id") == "guard")


def _run(stage, skill_dir, assign="flagsmith", environment="production"):
    env = {"PATH": "/usr/bin:/bin", "STAGE": stage, "SKILL_DIR": skill_dir, "ASSIGN": assign, "ENVIRONMENT": environment}
    return subprocess.run(["bash", "-e", "-c", _guard()["run"]], env=env, capture_output=True, text=True, check=False)


def test_guard_runs_before_the_matrix_and_reads_the_inputs():
    job = yaml.safe_load(WF.read_text())["jobs"]["prepare"]
    assert [s.get("id") for s in job["steps"]] == ["guard", "gen"]
    assert _guard()["env"] == {"STAGE": "${{ inputs.stage }}", "SKILL_DIR": "${{ inputs.skill_dir }}",
                               "ASSIGN": "${{ inputs.assign }}", "ENVIRONMENT": "${{ inputs.environment }}"}  # fmt: skip


@pytest.mark.parametrize("args", [
    ("primary", V1), ("replication", V1), ("primary", V1, "local", "development"), ("rollout", V1, "rollout"),
    ("primary", V1, "rollout"), ("followup", V2), ("followup", V2, "flagsmith", "development"),
    ("followup", V2, "local", "development"), ("primary", V2, "flagsmith", "development"),
])  # fmt: skip
def test_guard_allows(args):
    r = _run(*args)
    assert r.returncode == 0 and "guard ok" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("args", [
    ("followup", V1), ("followup", ""), ("followup", V2 + "/"), ("followup", V2, "rollout"),
    ("primary", V2), ("replication", V2), ("rollout", V2, "rollout"),
])  # fmt: skip
def test_guard_refuses(args):
    r = _run(*args)
    assert r.returncode == 1 and "guard ok" not in r.stdout, r.stdout + r.stderr
