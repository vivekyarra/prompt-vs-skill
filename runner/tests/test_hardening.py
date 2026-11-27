"""Stage field, non-UTF-8 robustness, and rollout assignment (mocked SDK client)."""

import json
import subprocess
import sys
import types

import pytest

from runner import agent, cli, grader_step, workspace
from runner.config import Limits, resolve_stage
from runner.flags import RolloutFlagsmithClient
from runner.trial import run_trial

from .conftest import PASS_RESULT, FakeCleaner, FakeFlagsmith

LIMITS = Limits(max_turns=5, max_tokens=1000, wall_s=60)


def _grader(monkeypatch):
    def fake(*a, **k):
        a[3].write_text(json.dumps(PASS_RESULT))
        return PASS_RESULT

    monkeypatch.setattr(grader_step, "run_grader", fake)


# ---------------------------------------------------------------- stage


def test_resolve_stage():
    assert resolve_stage({}) == "primary"
    assert resolve_stage({"HANDOFF_STAGE": ""}) == "primary"
    assert resolve_stage({"HANDOFF_STAGE": " Replication "}) == "replication"
    assert resolve_stage({"HANDOFF_STAGE": "rollout"}) == "rollout"
    assert resolve_stage({"HANDOFF_STAGE": "primary"}, assignment="rollout") == "rollout"
    with pytest.raises(ValueError):
        resolve_stage({"HANDOFF_STAGE": "pilot"})


@pytest.mark.parametrize("env,assignment,expected", [
    ({}, "flagsmith", "primary"),
    ({"HANDOFF_STAGE": "replication"}, "flagsmith", "replication"),
    ({"HANDOFF_STAGE": "primary"}, "rollout", "rollout"),
])  # fmt: skip
def test_record_has_stage(tmp_path, fixtures, monkeypatch, env, assignment, expected):
    _grader(monkeypatch)
    rec = run_trial("trial-5-0", tmp_path / "o", FakeFlagsmith(), FakeCleaner(), limits=LIMITS,
                    fake_agent=True, env=env, assignment=assignment, **fixtures)  # fmt: skip
    assert rec["stage"] == expected and rec["runner_error"] is False
    assert json.loads((tmp_path / "o" / "trial_record.json").read_text())["stage"] == expected


def test_invalid_stage_is_runner_error(tmp_path, fixtures, monkeypatch):
    _grader(monkeypatch)
    rec = run_trial("trial-5-1", tmp_path / "o", FakeFlagsmith(), FakeCleaner(), limits=LIMITS,
                    fake_agent=True, env={"HANDOFF_STAGE": "bogus"}, **fixtures)  # fmt: skip
    assert rec["runner_error"] is True and "stage" in rec["runner_error_message"]


# ---------------------------------------------------------------- non-UTF-8 bytes


def _git_repo(path):
    for args in (["init", "-q"], ["config", "user.name", "t"], ["config", "user.email", "t@invalid"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "a.txt").write_text("base\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "b"], cwd=path, check=True)


def test_capture_diff_survives_non_utf8_bytes(tmp_path):
    _git_repo(tmp_path)
    (tmp_path / "latin1.txt").write_bytes(b"micro sign: \xb5 \xe9\n")  # text diff with invalid UTF-8
    (tmp_path / "blob.bin").write_bytes(b"\x00\xff\xb5\x80")
    diff = workspace.capture_diff(tmp_path)
    assert "latin1.txt" in diff and "blob.bin" in diff and "�" in diff


def test_run_agent_survives_non_utf8_output(tmp_path):
    code = (
        "import sys\nsys.stdin.read()\n"
        "sys.stdout.buffer.write(b'{\"type\":\"noise\",\"x\":\"\\xb5\\xff\"}\\n')\nsys.stdout.flush()\n"
    )
    r = agent.run_agent([sys.executable, "-c", code], "hi", tmp_path, {"PATH": ""}, LIMITS)
    assert any("�" in ln for ln in r.raw_lines)


def test_trial_with_binary_and_non_utf8_workspace_files_does_not_crash(tmp_path, fixtures, monkeypatch):
    _grader(monkeypatch)
    real_prepare = workspace.prepare_workspace

    def prepare(*a, **k):
        ws = real_prepare(*a, **k)
        (ws / "latin1.txt").write_bytes(b"caf\xe9 \xb5\n")
        (ws / "blob.bin").write_bytes(bytes(range(256)))
        return ws

    monkeypatch.setattr(workspace, "prepare_workspace", prepare)
    rec = run_trial("trial-6-0", tmp_path / "o", FakeFlagsmith(), FakeCleaner(), limits=LIMITS,
                    fake_agent=True, env={}, **fixtures)  # fmt: skip
    assert rec["runner_error"] is False and rec["passed"] is True
    diff = (tmp_path / "o" / "diff.patch").read_text(encoding="utf-8")
    assert "latin1.txt" in diff


# ---------------------------------------------------------------- rollout


class _Flag:
    def __init__(self, value, variant=None):
        self.value, self.variant = value, variant


class _Flags:
    def __init__(self, flag):
        self.flag, self.asked = flag, []

    def get_flag(self, name):
        self.asked.append(name)
        return self.flag


class _MockSdk:
    """Mocks the parts of flagsmith.Flagsmith that rollout may use; anything else fails the test."""

    def __init__(self, flag):
        self.flags, self.calls = _Flags(flag), []

    def get_identity_flags(self, identifier, traits=None, *, transient=False):
        self.calls.append((identifier, traits, transient))
        return self.flags

    def get_experiment_flag(self, *a, **k):
        raise AssertionError("rollout must not use get_experiment_flag")

    def track_event(self, *a, **k):
        raise AssertionError("rollout must send no events")

    def flush_events(self):
        raise AssertionError("rollout must send no events")


def _rollout_client(monkeypatch, flag):
    monkeypatch.setenv("FS_EXPERIMENT_SERVER_KEY", "k")
    created = {}

    class FakeFlagsmithCls(_MockSdk):
        def __init__(self, **kw):
            created.update(kw)
            super().__init__(flag)

    monkeypatch.setitem(sys.modules, "flagsmith", types.SimpleNamespace(Flagsmith=FakeFlagsmithCls))
    return RolloutFlagsmithClient(), created


def test_rollout_client_plain_flag_read_no_events(monkeypatch):
    c, created = _rollout_client(monkeypatch, _Flag("skill", "skill"))
    assert created["enable_events"] is False
    r = c.get_exposure("trial-1", "node")
    assert (r.variant, r.in_experiment, r.raw_value) == ("skill", False, "skill")
    assert c._fs.calls == [("trial-1", {"stack": "node"}, True)]
    assert c._fs.flags.asked == ["onboarding_method"]
    c.send_event("integration_verified", "trial-1", "node")  # no-ops, would raise via the mock otherwise
    c.flush()
    c.close()


def test_rollout_client_control_value_prompt_and_unknown(monkeypatch):
    c, _ = _rollout_client(monkeypatch, _Flag("prompt", "control"))
    assert c.get_exposure("t", "react").variant == "prompt"
    c2, _ = _rollout_client(monkeypatch, _Flag("something", None))
    with pytest.raises(RuntimeError):
        c2.get_exposure("t", "react")


def test_rollout_client_needs_key(monkeypatch):
    monkeypatch.delenv("FS_EXPERIMENT_SERVER_KEY", raising=False)
    with pytest.raises(RuntimeError):
        RolloutFlagsmithClient()


def test_resolve_assign_rollout_allowed_anywhere():
    assert cli.resolve_assign("rollout", {"HANDOFF_ENVIRONMENT": "production"}) == "rollout"
    assert cli.resolve_assign(None, {"HANDOFF_ASSIGN": "rollout", "HANDOFF_ENVIRONMENT": "development"}) == "rollout"


def test_run_trial_rollout_records_and_sends_nothing(tmp_path, fixtures, monkeypatch):
    _grader(monkeypatch)
    fs = FakeFlagsmith("skill")
    rec = run_trial("trial-9-0", tmp_path / "o", fs, FakeCleaner(), limits=LIMITS, fake_agent=True,
                    env={"HANDOFF_STAGE": "primary", "HANDOFF_ENVIRONMENT": "production"},
                    assignment="rollout", **fixtures)  # fmt: skip
    assert rec["assignment"] == "rollout" and rec["stage"] == "rollout"
    assert rec["runner_error"] is False and rec["variant"] == "skill"
    assert rec["events_sent"] == [] and rec["events_would_send"] == ["integration_verified"]


def test_cli_rollout_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDOFF_ENVIRONMENT", "production")
    monkeypatch.setenv("HANDOFF_STAGE", "primary")
    rc = cli.main(["--trial-id", "trial-7-1", "--out-dir", str(tmp_path / "o"), "--assign", "rollout",
                   "--dry-run", "--skip-grader"])  # fmt: skip
    rec = json.loads((tmp_path / "o" / "trial_record.json").read_text())
    assert rc in (0, 1) and rec["assignment"] == "rollout" and rec["stage"] == "rollout"
    assert rec["events_sent"] == [] and not (tmp_path / "o" / "dry_run_events.json").exists()
