import json
import subprocess
import sys
import textwrap
from collections import Counter

import pytest

from runner import agent, grader_step, workspace
from runner.config import STACKS, Limits
from runner.events import decide_events, send_events
from runner.stack import pick_stack
from runner.trial import RECORD_FIELDS, run_trial

from .conftest import PASS_RESULT, StubCleaner, StubFlagsmith

LIMITS = Limits(max_turns=5, max_tokens=1000, wall_s=60)


# ---- stack selection
def test_stack_deterministic_and_uniform():
    ids = [f"trial-123-{i}" for i in range(3000)]
    assert [pick_stack(i) for i in ids] == [pick_stack(i) for i in ids]
    c = Counter(pick_stack(i) for i in ids)
    assert set(c) == set(STACKS)
    for s in STACKS:
        assert 850 < c[s] < 1150, c


# ---- limits
def test_evaluate_limits():
    L = Limits(10, 100, 60)
    assert agent.evaluate_limits(10, 100, 60, L) == "none"
    assert agent.evaluate_limits(11, 0, 0, L) == "turns"
    assert agent.evaluate_limits(0, 101, 0, L) == "tokens"
    assert agent.evaluate_limits(0, 0, 61, L) == "time"


def _stub_claude(tmp_path, body):
    p = tmp_path / "stub_claude.py"
    p.write_text(textwrap.dedent(body))
    return [sys.executable, str(p)]


def _assistant(i, out=10):
    m = {"id": f"m{i}", "usage": {"input_tokens": 1, "output_tokens": out}}
    return json.dumps({"type": "assistant", "message": m})


def test_run_agent_kills_on_turns(tmp_path):
    cmd = _stub_claude(
        tmp_path,
        f"""
        import sys, time
        sys.stdin.read()
        for i in range(50):
            print({_assistant(0)!r}.replace("m0", f"m{{i}}"), flush=True)
            time.sleep(0.01)
        time.sleep(30)
        """,
    )
    r = agent.run_agent(cmd, "hi", tmp_path, {"PATH": ""}, LIMITS)
    assert r.limit_hit == "turns" and r.over_budget and r.turns == 6


def test_run_agent_kills_on_tokens(tmp_path):
    line = _assistant(1, out=5000)
    cmd = _stub_claude(
        tmp_path,
        f"""
        import sys, time
        sys.stdin.read()
        print({line!r}, flush=True)
        time.sleep(30)
        """,
    )
    r = agent.run_agent(cmd, "hi", tmp_path, {}, LIMITS)
    assert r.limit_hit == "tokens"


def test_run_agent_kills_on_wall_time(tmp_path):
    cmd = _stub_claude(tmp_path, "import sys,time\nsys.stdin.read()\ntime.sleep(30)\n")
    r = agent.run_agent(cmd, "hi", tmp_path, {}, Limits(5, 1000, wall_s=1))
    assert r.limit_hit == "time" and r.duration_s < 10


def test_run_agent_clean_finish_parses_result(tmp_path):
    res = {"type": "result", "subtype": "success", "num_turns": 2, "total_cost_usd": 0.5,
           "result": "DONE", "usage": {"input_tokens": 10, "output_tokens": 20,
                                       "cache_creation_input_tokens": 5, "cache_read_input_tokens": 7}}  # fmt: skip
    cmd = _stub_claude(
        tmp_path,
        f"import sys\nsys.stdin.read()\nprint({_assistant(1)!r})\nprint({json.dumps(res)!r})\n",
    )
    r = agent.run_agent(cmd, "hi", tmp_path, {}, LIMITS)
    assert (r.turns, r.input_tokens, r.output_tokens, r.cost_usd) == (2, 22, 20, 0.5)
    assert r.limit_hit == "none" and r.final_text == "DONE" and r.exit_code == 0


def test_max_turns_subtype_counts_as_limit(tmp_path):
    res = {"type": "result", "subtype": "error_max_turns", "num_turns": 5, "usage": {}}
    cmd = _stub_claude(tmp_path, f"import sys\nsys.stdin.read()\nprint({json.dumps(res)!r})\n")
    assert agent.run_agent(cmd, "x", tmp_path, {}, LIMITS).limit_hit == "turns"


# ---- event logic
@pytest.mark.parametrize(
    "passed,limit,err,expected",
    [
        (True, "none", False, ["integration_verified"]),
        (False, "none", False, []),
        (False, "turns", False, ["over_budget"]),
        (True, "time", False, ["integration_verified", "over_budget"]),
        (True, "none", True, []),
        (False, "tokens", True, []),
    ],
)
def test_decide_events(passed, limit, err, expected):
    assert decide_events(passed, limit, err) == expected


def test_send_events_flush_confirmation():
    fs = StubFlagsmith()
    sent, ok = send_events(fs, ["integration_verified"], "t", "node")
    assert sent == ["integration_verified"] and ok and fs.flushed == 1
    assert fs.events == [("integration_verified", "t", "node")]
    sent, ok = send_events(StubFlagsmith(flush_error=True), ["over_budget"], "t", "node")
    assert sent == [] and not ok


# ---- instruction assembly and workspace
def test_brief_identical_in_both_variants_and_placeholders_filled(fixtures):
    brief, sha = workspace.load_brief(fixtures["brief_path"], "trial-9-1")
    prompt, _ = workspace.load_official_prompt(fixtures["prompt_path"])
    a = workspace.build_instruction("prompt", prompt, brief)
    b = workspace.build_instruction("skill", prompt, brief)
    assert a.endswith(brief) and b.endswith(brief)
    assert "join_button_trial_9_1" in brief and "{{" not in brief
    assert a.startswith("OFFICIAL TEXT") and "header meta" not in a and "footer" not in a
    assert b.startswith(workspace.SKILL_USER_PROMPT) and "OFFICIAL TEXT" not in b
    assert len(sha) == 64


def test_prompt_without_markers_uses_whole_file(tmp_path):
    p = tmp_path / "p.md"
    p.write_text("whole file")
    assert workspace.load_official_prompt(p)[0] == "whole file"


def test_unresolved_placeholder_fails():
    with pytest.raises(ValueError):
        workspace.render_brief("x {{NOPE}}", "t")


def test_skill_installed_only_for_variant_b(fixtures, tmp_path):
    kw = {"apps_dir": fixtures["apps_dir"], "skill_dir": fixtures["skill_dir"]}
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    wa = workspace.prepare_workspace(tmp_path / "a", "node", "prompt", **kw)
    wb = workspace.prepare_workspace(tmp_path / "b", "node", "skill", **kw)
    assert not (wa / ".claude").exists()
    assert (wb / ".claude" / "skills" / "flagsmith-ab-test" / "SKILL.md").is_file()
    assert (wa / "app.txt").read_text() == "baseline node\n"
    # the skill is in the baseline commit, so it is not part of the agent's diff
    (wb / "new.txt").write_text("x")
    d = workspace.capture_diff(wb)
    assert "new.txt" in d and "SKILL.md" not in d
    assert subprocess.run(["git", "log", "--oneline"], cwd=wb, capture_output=True, text=True, check=False).stdout


# ---- env scrubbing
def test_agent_env_never_contains_experiment_key():
    src = {
        "FS_EXPERIMENT_SERVER_KEY": "EXPSECRET", "FS_SANDBOX_CLIENT_KEY": "c", "FS_SANDBOX_SERVER_KEY": "s",
        "FS_SANDBOX_ADMIN_KEY": "a", "FS_SANDBOX_PROJECT_ID": "1", "ANTHROPIC_API_KEY": "k",
        "PATH": "/bin", "GITHUB_TOKEN": "gh", "HANDOFF_MAX_TURNS": "5", "RANDOM_OTHER": "x",
    }  # fmt: skip
    env = agent.build_agent_env(src)
    assert "FS_EXPERIMENT_SERVER_KEY" not in env and "EXPSECRET" not in env.values()
    assert set(env) == {"FS_SANDBOX_CLIENT_KEY", "FS_SANDBOX_SERVER_KEY", "FS_SANDBOX_ADMIN_KEY",
                        "FS_SANDBOX_PROJECT_ID", "ANTHROPIC_API_KEY", "PATH", "FLAGSMITH_CLIENT_KEY",
                        "FLAGSMITH_SERVER_KEY", "FLAGSMITH_API_KEY", "FLAGSMITH_PROJECT_ID"}  # fmt: skip


def test_agent_command_tools_identical_regardless_of_variant():
    cmd = agent.build_command("m", 7)
    assert cmd[cmd.index("--max-turns") + 1] == "7" and "Skill" in cmd[cmd.index("--tools") + 1]
    assert cmd == agent.build_command("m", 7)


# ---- full trial (scripted agent) and record schema
def _run(tmp_path, fixtures, monkeypatch, variant="prompt", grader=PASS_RESULT, scripted_agent_fn=None, **kw):
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: _write(a[3], grader))
    fs, cl = StubFlagsmith(variant), StubCleaner()
    rec = run_trial("trial-1-0", tmp_path / "out", fs, cl, limits=LIMITS, scripted_agent=True,
                    env={"FS_EXPERIMENT_SERVER_KEY": "EXPSECRET"}, **fixtures, **kw)  # fmt: skip
    return rec, fs, cl


def _write(path, obj):
    path.write_text(json.dumps(obj))
    return obj


def test_record_schema_and_events_on_pass(tmp_path, fixtures, monkeypatch):
    rec, fs, cl = _run(tmp_path, fixtures, monkeypatch, variant="skill")
    on_disk = json.loads((tmp_path / "out" / "trial_record.json").read_text())
    assert on_disk == rec
    for f in RECORD_FIELDS:
        assert f in rec, f
    assert rec["variant"] == "skill" and rec["passed"] is True and rec["runner_error"] is False
    assert rec["checks"] == {f"C{i}": True for i in range(1, 8)}
    assert rec["events_sent"] == ["integration_verified"] and rec["limit_hit"] == "none"
    assert fs.events == [("integration_verified", "trial-1-0", rec["stack"])] and fs.flushed == 1
    assert cl.deleted == ["join_button_trial_1_0"] and len(rec["brief_sha256"]) == 64
    assert (tmp_path / "out" / "diff.patch").is_file()


def test_failed_grader_sends_no_events(tmp_path, fixtures, monkeypatch):
    bad = {"passed": False, "checks": {"C1": {"passed": False, "reason": "no sdk"}}}
    rec, fs, _ = _run(tmp_path, fixtures, monkeypatch, grader=bad)
    assert rec["passed"] is False and rec["events_sent"] == [] and fs.events == []
    assert rec["failure_reasons"][0] == "C1: no sdk" and rec["checks"]["C2"] is False


def test_over_budget_event(tmp_path, fixtures, monkeypatch):
    monkeypatch.setattr(
        agent, "scripted_agent_result", lambda: agent.AgentResult(limit_hit="tokens", exit_code=-9)
    )
    bad = {"passed": False, "checks": {}}
    rec, _fs, _ = _run(tmp_path, fixtures, monkeypatch, grader=bad)
    assert rec["over_budget"] is True and rec["limit_hit"] == "tokens"
    assert rec["events_sent"] == ["over_budget"]


def test_runner_error_sends_no_event_and_keeps_record(tmp_path, fixtures, monkeypatch):
    def boom(*a, **k):
        raise grader_step.GraderError("grader exploded")

    monkeypatch.setattr(grader_step, "run_grader", boom)
    fs, cl = StubFlagsmith(), StubCleaner()
    rec = run_trial("trial-2-0", tmp_path / "o", fs, cl, limits=LIMITS, scripted_agent=True,
                    env={}, **fixtures)  # fmt: skip
    assert rec["runner_error"] is True and "grader exploded" in rec["runner_error_message"]
    assert fs.events == [] and rec["events_sent"] == [] and cl.deleted
    assert json.loads((tmp_path / "o" / "trial_record.json").read_text())["runner_error"] is True


def test_flush_failure_is_runner_error(tmp_path, fixtures, monkeypatch):
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: _write(a[3], PASS_RESULT))
    fs = StubFlagsmith(flush_error=True)
    rec = run_trial("trial-3-0", tmp_path / "o", fs, StubCleaner(), limits=LIMITS, scripted_agent=True,
                    env={}, **fixtures)  # fmt: skip
    assert rec["runner_error"] and rec["events_sent"] == [] and rec["events_flush_confirmed"] is False


def test_exposure_retried_only_before_agent(tmp_path, fixtures):
    class Flaky(StubFlagsmith):
        n = 0

        def get_exposure(self, t, s):
            Flaky.n += 1
            if Flaky.n < 3:
                raise OSError("net")
            return super().get_exposure(t, s)

    rec = run_trial("trial-4-0", tmp_path / "o", Flaky(), StubCleaner(), limits=LIMITS, scripted_agent=True,
                    skip_grader=True, env={}, sleep=lambda s: None, **fixtures)  # fmt: skip
    assert Flaky.n == 3 and rec["runner_error"] is False and rec["grader_skipped"] is True


def test_dry_run_cli(tmp_path):
    out = tmp_path / "o"
    r = subprocess.run([sys.executable, "-m", "runner", "--trial-id", "trial-5-0", "--out-dir", str(out),
                        "--dry-run", "--skip-grader"],
                       capture_output=True, text=True, cwd=workspace.REPO_ROOT, check=False)  # fmt: skip
    rec = json.loads((out / "trial_record.json").read_text())
    # Baseline apps/prompt/brief may not exist in this branch; either a clean record or a recorded error.
    assert rec["trial_id"] == "trial-5-0" and rec["dry_run"] is True
    assert r.returncode == (1 if rec["runner_error"] else 0)


def test_agent_env_maps_ci_secret_names_to_brief_names():
    src = {
        "FS_SANDBOX_CLIENT_KEY": "c", "FS_SANDBOX_SERVER_KEY": "s", "FS_SANDBOX_ADMIN_KEY": "a",
        "FS_SANDBOX_PROJECT_ID": "p", "FS_EXPERIMENT_SERVER_KEY": "never", "PATH": "/bin",
    }  # fmt: skip
    env = agent.build_agent_env(src)
    assert env["FLAGSMITH_CLIENT_KEY"] == "c"
    assert env["FLAGSMITH_SERVER_KEY"] == "s"
    assert env["FLAGSMITH_API_KEY"] == "a"
    assert env["FLAGSMITH_PROJECT_ID"] == "p"
    assert "FS_EXPERIMENT_SERVER_KEY" not in env


# ---- local assignment pilot
def test_resolve_assign():
    from runner.cli import resolve_assign

    assert resolve_assign(None, {}) == "flagsmith"
    assert resolve_assign(None, {"HANDOFF_ASSIGN": "local"}) == "local"
    assert resolve_assign("local", {"HANDOFF_ENVIRONMENT": "development"}) == "local"
    assert resolve_assign("flagsmith", {"HANDOFF_ENVIRONMENT": "production"}) == "flagsmith"
    with pytest.raises(ValueError, match="production"):
        resolve_assign("local", {"HANDOFF_ENVIRONMENT": "production"})
    with pytest.raises(ValueError, match="production"):
        resolve_assign(None, {"HANDOFF_ASSIGN": "local", "HANDOFF_ENVIRONMENT": " Production "})
    with pytest.raises(ValueError):
        resolve_assign("bogus", {})


def test_local_assignment_balanced_deterministic():
    from runner.cli import LocalAssignment

    la = LocalAssignment()
    vs = [la.get_exposure(f"trial-9-{i}", "x").variant for i in range(2000)]
    assert vs == [la.get_exposure(f"trial-9-{i}", "x").variant for i in range(2000)]
    assert 900 < vs.count("prompt") < 1100 and set(vs) == {"prompt", "skill"}


def _cli(tmp_path, environment, *args):
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("HANDOFF_ENVIRONMENT", "HANDOFF_ASSIGN")}
    env["HANDOFF_ENVIRONMENT"] = environment
    return subprocess.run([sys.executable, "-m", "runner", "--trial-id", "trial-7-1", "--out-dir",
                           str(tmp_path / "o"), *args],
                          capture_output=True, text=True, cwd=workspace.REPO_ROOT, env=env, check=False)  # fmt: skip


def test_cli_refuses_local_in_production(tmp_path):
    r = _cli(tmp_path, "production", "--assign", "local", "--dry-run")
    assert r.returncode == 2 and "production" in r.stderr
    assert not (tmp_path / "o" / "trial_record.json").exists()


def test_cli_local_dry_run_record_and_marker(tmp_path):
    r = _cli(tmp_path, "development", "--assign", "local", "--dry-run", "--skip-grader")
    assert "TRIAL_RECORD_JSON:" in r.stdout
    printed = json.loads(r.stdout.split("TRIAL_RECORD_JSON:\n", 1)[1])
    rec = json.loads((tmp_path / "o" / "trial_record.json").read_text())
    assert printed["assignment"] == rec["assignment"] == "local"
    assert rec["events_sent"] == []
    assert not (tmp_path / "o" / "dry_run_events.json").exists()
    if not rec["runner_error"]:
        assert rec["variant"] in ("prompt", "skill")


def test_run_trial_local_never_sends_events(tmp_path):
    fs = StubFlagsmith()
    rec = run_trial("trial-8-0", tmp_path / "o", fs, StubCleaner(), limits=LIMITS, scripted_agent=True,
                    skip_grader=True, env={}, assignment="local")  # fmt: skip
    if not rec["runner_error"]:
        assert rec["assignment"] == "local" and rec["events_sent"] == []


def test_agent_provider_error_is_runner_error_not_failed_integration(tmp_path, fixtures, monkeypatch):
    monkeypatch.setattr(
        agent, "scripted_agent_result",
        lambda: agent.AgentResult(result_subtype="error", exit_code=1, final_text="Expected 'id' to be a string."),
    )  # fmt: skip
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: _write(a[3], PASS_RESULT))
    fs, cl = StubFlagsmith(), StubCleaner()
    rec = run_trial("trial-4-0", tmp_path / "o", fs, cl, limits=LIMITS, scripted_agent=True,
                    env={}, **fixtures)  # fmt: skip
    assert rec["runner_error"] is True and "agent infrastructure error" in rec["runner_error_message"]
    assert fs.events == [] and rec["events_sent"] == [] and cl.deleted


def test_zero_turn_real_agent_run_is_runner_error(tmp_path, fixtures, monkeypatch):
    from runner import agents  # noqa: F401

    monkeypatch.setattr(agent, "run_agent", lambda *a, **k: agent.AgentResult(exit_code=1, turns=0))
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: _write(a[3], PASS_RESULT))
    fs, cl = StubFlagsmith(), StubCleaner()
    rec = run_trial("trial-5-0", tmp_path / "o", fs, cl, limits=LIMITS, scripted_agent=False,
                    env={"HANDOFF_AGENT": "claude"}, claude_bin="true", **fixtures)  # fmt: skip
    assert rec["runner_error"] is True and fs.events == []
