import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"


def load(name):
    data = yaml.safe_load((WF / name).read_text())
    # PyYAML parses the bare key `on` as boolean True
    data["on"] = data.get("on", data.get(True))
    return data


@pytest.mark.parametrize("name", sorted(p.name for p in WF.glob("*.yml")))
def test_yaml_parses(name):
    d = load(name)
    assert d["jobs"]


def test_trials_workflow_shape():
    d = load("trials.yml")
    inputs = d["on"]["workflow_dispatch"]["inputs"]
    assert {"count", "environment"} <= set(inputs)
    assert inputs["environment"]["options"] == ["development", "production"]
    assert inputs["assign"]["options"] == ["flagsmith", "local", "rollout"]
    assert inputs["stage"]["default"] == "primary"
    assert inputs["stage"]["options"] == ["primary", "replication", "rollout"]
    assert d["jobs"]["trial"]["env"]["HANDOFF_STAGE"] == "${{ inputs.stage }}"
    job = d["jobs"]["trial"]
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["max-parallel"] == 5
    assert job["timeout-minutes"] == 45
    assert "prepare" in d["jobs"]
    text = (WF / "trials.yml").read_text()
    for needle in ("python -m runner --trial-id", "--out-dir out", "FS_EXPERIMENT_SERVER_KEY",
                   "FS_SANDBOX_ADMIN_KEY", "HANDOFF_MAX_TURNS", "@anthropic-ai/claude-code",
                   "get.flagsmith.com", "playwright"):
        assert needle in text


def test_collect_never_pushes_to_main():
    text = (WF / "collect.yml").read_text()
    assert "HEAD:data" in text
    assert "origin main" not in text and "HEAD:main" not in text
    d = load("collect.yml")
    assert "workflow_run" in d["on"] and "workflow_dispatch" in d["on"]


def test_no_hardcoded_secrets():
    for p in WF.glob("*.yml"):
        for line in p.read_text().splitlines():
            if "KEY" in line and ":" in line and "secrets." not in line:
                assert line.strip().endswith(("KEY", "KEY:")) or "${{" in line or "#" in line or "needle" in line
