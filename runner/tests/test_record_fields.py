"""Record-only fields: skill_tool_calls/skill_loaded and flag_exists_at_cleanup/flag_created_during_trial."""

import json
from datetime import datetime, timedelta, timezone

from runner import flags, grader_step
from runner.skill_usage import count_skill_calls
from runner.trial import flag_created_during, run_trial

from .conftest import PASS_RESULT, FakeCleaner, FakeFlagsmith
from .test_runner import LIMITS, _write


def oc(call_id, name, tool="skill"):
    return json.dumps({"type": "tool_use", "part": {"tool": tool, "callID": call_id,
                                                    "state": {"input": {"name": name}}}})


def test_opencode_skill_calls_counted():
    lines = [oc("a", "flagsmith-ab-test"), oc("a", "flagsmith-ab-test"), oc("b", "other"),
             oc("c", "x", tool="bash"), "not json", json.dumps({"type": "text", "part": {"text": "hi"}})]
    assert count_skill_calls(lines, "flagsmith-ab-test") == (2, True)
    assert count_skill_calls([oc("b", "other")], "flagsmith-ab-test") == (1, False)
    assert count_skill_calls([], "flagsmith-ab-test") == (0, False)


def test_claude_skill_calls_counted():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "flagsmith-ab-test"}},
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ls"}}]}}
    assert count_skill_calls([json.dumps(ev)], "flagsmith-ab-test") == (1, True)


class InfoCleaner(FakeCleaner):
    def __init__(self, info):
        super().__init__()
        self.info = info

    def inspect_flag(self, name):
        return self.info


def _trial(tmp_path, fixtures, monkeypatch, cleaner):
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: _write(a[3], PASS_RESULT))
    return run_trial("trial-1-0", tmp_path / "o", FakeFlagsmith("prompt"), cleaner, limits=LIMITS,
                     fake_agent=True, env={"FS_EXPERIMENT_SERVER_KEY": "X"}, **fixtures)


def test_legacy_cleaner_leaves_unknown(tmp_path, fixtures, monkeypatch):
    rec = _trial(tmp_path, fixtures, monkeypatch, FakeCleaner())
    assert rec["flag_exists_at_cleanup"] is None and rec["flag_created_during_trial"] is None
    assert rec["cleanup_status"] == "deleted" and rec["skill_tool_calls"] == 0 and rec["skill_loaded"] is False


def test_created_during_trial_recorded(tmp_path, fixtures, monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    rec = _trial(tmp_path, fixtures, monkeypatch, InfoCleaner({"exists": True, "created_date": future}))
    assert rec["flag_exists_at_cleanup"] is True and rec["flag_created_during_trial"] is True
    rec = _trial(tmp_path, fixtures, monkeypatch, InfoCleaner({"exists": True, "created_date": "2020-01-01T00:00:00Z"}))
    assert rec["flag_created_during_trial"] is False
    rec = _trial(tmp_path, fixtures, monkeypatch, InfoCleaner({"exists": True, "created_date": None}))
    assert rec["flag_exists_at_cleanup"] is True and rec["flag_created_during_trial"] is None
    rec = _trial(tmp_path, fixtures, monkeypatch, InfoCleaner({"exists": False, "created_date": None}))
    assert rec["flag_exists_at_cleanup"] is False and rec["flag_created_during_trial"] is None


def test_inspect_errors_never_affect_cleanup(tmp_path, fixtures, monkeypatch):
    class Boom(FakeCleaner):
        def inspect_flag(self, name):
            raise RuntimeError("x")

    rec = _trial(tmp_path, fixtures, monkeypatch, Boom())
    assert rec["flag_exists_at_cleanup"] is None and rec["cleanup_status"] == "deleted"


def test_flag_created_during_parsing():
    t = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    assert flag_created_during("2026-11-27T12:00:00Z", t) is True
    assert flag_created_during("2026-11-27T11:59:59.5+00:00", t) is False
    assert flag_created_during("2026-11-27T12:00:01", t) is True  # naive treated as UTC
    assert flag_created_during("garbage", t) is None and flag_created_during(None, t) is None


def test_admin_cleaner_inspect_with_mocked_api():
    c = flags.AdminApiCleaner("k", "1")
    calls = []

    def fake(method, path):
        calls.append(method)
        return {"results": [{"id": 1, "name": "f_a", "created_date": "2026-11-27T12:00:00Z"},
                            {"id": 2, "name": "f_ab"}]}

    c._req = fake
    assert c.inspect_flag("f_a") == {"exists": True, "created_date": "2026-11-27T12:00:00Z"}
    assert c.inspect_flag("f_ab") == {"exists": True, "created_date": None}
    assert c.inspect_flag("zzz") == {"exists": False, "created_date": None}
    assert set(calls) == {"GET"}

    def boom(method, path):
        raise OSError("down")

    c._req = boom
    assert c.inspect_flag("f_a") is None
    assert flags.NoopCleaner().inspect_flag("f_a") is None


def test_resolve_skill_dir_default_and_override():
    import pytest

    from runner.config import DEFAULT_SKILL_DIR, resolve_skill_dir

    assert resolve_skill_dir({}) == DEFAULT_SKILL_DIR == "skill/flagsmith-ab-test"
    assert resolve_skill_dir({"HANDOFF_SKILL_DIR": ""}) == DEFAULT_SKILL_DIR
    assert resolve_skill_dir({"HANDOFF_SKILL_DIR": "skill/flagsmith-ab-test-v2/"}) == "skill/flagsmith-ab-test-v2"
    for bad in ("/etc", "../x", "skill/../x", "other/foo", "skill/a/b"):
        with pytest.raises(ValueError):
            resolve_skill_dir({"HANDOFF_SKILL_DIR": bad})


def test_record_skill_dir_from_env_and_installed_name(tmp_path, fixtures, monkeypatch):
    """HANDOFF_SKILL_DIR selects the folder (recorded); the folder is installed as flagsmith-ab-test."""
    from runner import trial

    repo = tmp_path / "repo"
    (repo / "skill" / "flagsmith-ab-test-v2").mkdir(parents=True)
    (repo / "skill" / "flagsmith-ab-test-v2" / "SKILL.md").write_text("# v2 marker\n")
    monkeypatch.setattr(trial, "REPO_ROOT", repo)
    seen = {}
    real = trial.workspace.prepare_workspace

    def spy(work_dir, stack, variant, apps_dir=None, skill_dir=None, **kw):
        seen["skill_dir"] = skill_dir
        ws = real(work_dir, stack, variant, apps_dir, skill_dir, **kw)
        seen["text"] = (ws / ".claude" / "skills" / "flagsmith-ab-test" / "SKILL.md").read_text()
        return ws

    monkeypatch.setattr(trial.workspace, "prepare_workspace", spy)
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: _write(a[3], PASS_RESULT))
    fx = {k: v for k, v in fixtures.items() if k != "skill_dir"}
    env = {"FS_EXPERIMENT_SERVER_KEY": "X", "HANDOFF_SKILL_DIR": "skill/flagsmith-ab-test-v2"}
    rec = run_trial("trial-1-0", tmp_path / "o", FakeFlagsmith("skill"), FakeCleaner(), limits=LIMITS,
                    fake_agent=True, env=env, **fx)
    assert rec["skill_dir"] == "skill/flagsmith-ab-test-v2"
    assert seen["skill_dir"] == repo / "skill" / "flagsmith-ab-test-v2" and seen["text"] == "# v2 marker\n"


def test_record_skill_dir_default(tmp_path, fixtures, monkeypatch):
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: _write(a[3], PASS_RESULT))
    fx = {k: v for k, v in fixtures.items() if k != "skill_dir"}
    rec = run_trial("trial-1-0", tmp_path / "o", FakeFlagsmith("prompt"), FakeCleaner(), limits=LIMITS,
                    fake_agent=True, env={"FS_EXPERIMENT_SERVER_KEY": "X"}, **fx)
    assert rec["skill_dir"] == "skill/flagsmith-ab-test"
