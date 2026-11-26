"""Agent backends: OpenCode + Nebius adapter and backend selection. No network, no real keys."""

import json
import os
import pathlib
import stat
import subprocess
import sys
import textwrap

import pytest

from runner import agent, agents, grader_step, workspace
from runner.agents.base import price_cost
from runner.agents.opencode import OpenCodeBackend, OpenCodeTally, build_config
from runner.config import Limits
from runner.trial import run_trial

from .conftest import PASS_RESULT, FakeCleaner, FakeFlagsmith

LIMITS = Limits(max_turns=5, max_tokens=1000, wall_s=60)
SECRETS = {
    "FS_EXPERIMENT_SERVER_KEY": "EXPSECRET", "FS_SANDBOX_CLIENT_KEY": "cl-key", "FS_SANDBOX_SERVER_KEY": "sv-key",
    "FS_SANDBOX_ADMIN_KEY": "ad-key", "FS_SANDBOX_PROJECT_ID": "proj-77", "NEBIUS_API_KEY": "NEBSECRET",
    "ANTHROPIC_API_KEY": "ANTSECRET", "PATH": "/bin", "GITHUB_TOKEN": "gh", "RANDOM_OTHER": "x",
}  # fmt: skip


def step_finish(i, inp=10, out=5, reasoning=0, read=0, write=0, reason="tool-calls", cost=0):
    tokens = {"total": 0, "input": inp, "output": out, "reasoning": reasoning,
              "cache": {"write": write, "read": read}}  # fmt: skip
    part = {"id": f"prt_{i}", "reason": reason, "type": "step-finish", "tokens": tokens, "cost": cost}
    return json.dumps({"type": "step_finish", "sessionID": "ses_1", "part": part})


def text_event(t):
    return json.dumps({"type": "text", "part": {"type": "text", "text": t}})


def fake_cmd(tmp_path, body):
    p = tmp_path / "fake_opencode.py"
    p.write_text(textwrap.dedent(body))
    return [sys.executable, str(p)]


# ---- usage parsing
def test_tally_sums_cache_and_reasoning_and_dedupes_by_part_id():
    t = OpenCodeTally()
    for ln in (step_finish(1, inp=70, out=15, reasoning=5, read=30), step_finish(1, inp=70, out=15, reasoning=5, read=30),
               step_finish(2, inp=10, out=5, write=2, cost=0.25, reason="stop"), text_event("DONE"), "not json", "[]"):  # fmt: skip
        t.feed(ln)
    assert t.live() == (2, (70 + 30 + 10 + 2) + (15 + 5 + 5))
    r = agent.AgentResult()
    assert t.fill(r) is True
    assert (r.input_tokens, r.output_tokens, r.cache_read_tokens) == (112, 25, 30)
    assert r.cost_usd == 0.25 and r.final_text == "DONE" and r.result_subtype == "success"


def test_tally_error_event_and_no_events():
    t = OpenCodeTally()
    t.feed(json.dumps({"type": "error", "error": {"name": "APIError", "data": {"message": "ECONNREFUSED"}}}))
    r = agent.AgentResult()
    assert t.fill(r) and r.result_subtype == "error" and r.final_text == "ECONNREFUSED"
    assert OpenCodeTally().fill(agent.AgentResult()) is False


# ---- limit enforcement: identical logic to Claude (same run_agent, same evaluate_limits)
def test_opencode_events_kill_on_turns(tmp_path):
    cmd = fake_cmd(tmp_path, f"""
        import sys, time
        sys.stdin.read()
        for i in range(50):
            print({step_finish(0)!r}.replace("prt_0", f"prt_{{i}}"), flush=True)
            time.sleep(0.01)
        time.sleep(30)
        """)  # fmt: skip
    r = agent.run_agent(cmd, "hi", tmp_path, {"PATH": ""}, LIMITS, tally=OpenCodeTally())
    assert r.limit_hit == "turns" and r.over_budget and r.turns == 6


def test_opencode_events_kill_on_tokens(tmp_path):
    line = step_finish(1, inp=10, out=5000)
    cmd = fake_cmd(tmp_path, f"import sys, time\nsys.stdin.read()\nprint({line!r}, flush=True)\ntime.sleep(30)\n")
    r = agent.run_agent(cmd, "hi", tmp_path, {}, LIMITS, tally=OpenCodeTally())
    assert r.limit_hit == "tokens"


def test_opencode_events_kill_on_wall_time(tmp_path):
    cmd = fake_cmd(tmp_path, "import sys,time\nsys.stdin.read()\ntime.sleep(30)\n")
    r = agent.run_agent(cmd, "hi", tmp_path, {}, Limits(5, 1000, wall_s=1), tally=OpenCodeTally())
    assert r.limit_hit == "time" and r.duration_s < 10


def test_opencode_clean_finish(tmp_path):
    lines = [step_finish(1, inp=70, out=15, read=30), step_finish(2, out=2, reason="stop"), text_event("DONE")]
    cmd = fake_cmd(tmp_path, "import sys\nsys.stdin.read()\n" + "".join(f"print({ln!r})\n" for ln in lines))
    r = agent.run_agent(cmd, "hi", tmp_path, {}, LIMITS, tally=OpenCodeTally())
    assert r.limit_hit == "none" and r.turns == 2 and r.exit_code == 0 and r.final_text == "DONE"
    assert (r.input_tokens, r.output_tokens) == (110, 17)


def test_instruction_is_fed_on_stdin(tmp_path):
    body = "import sys\nprint(" + repr(text_event("@@")) + ".replace('@@', sys.stdin.read()))\n"
    r = agent.run_agent(fake_cmd(tmp_path, body), "THE INSTRUCTION", tmp_path, {}, LIMITS, tally=OpenCodeTally())
    assert r.final_text == "THE INSTRUCTION"


# ---- command building
def test_opencode_command():
    cmd = OpenCodeBackend("oc").build_command("Org/Some-Model", 7)
    assert cmd[:2] == ["oc", "run"] and "--pure" in cmd
    assert cmd[cmd.index("--format") + 1] == "json"
    assert cmd[cmd.index("-m") + 1] == "nebius/Org/Some-Model"
    assert "--title" in cmd  # no hidden title-generation model call
    assert "7" not in cmd  # turns are enforced by the runner, not by the CLI
    assert cmd == OpenCodeBackend("oc").build_command("Org/Some-Model", 7)


def test_claude_backend_command_unchanged():
    b = agents.get_backend("claude", "cc")
    assert b.build_command("m", 7) == agent.build_command("m", 7, "cc")


# ---- env scrubbing
def test_opencode_env_has_nebius_key_but_never_experiment_or_anthropic_key():
    env = OpenCodeBackend().build_env(SECRETS, model="Org/M")
    assert env["NEBIUS_API_KEY"] == "NEBSECRET"
    assert "FS_EXPERIMENT_SERVER_KEY" not in env and "EXPSECRET" not in env.values()
    assert "ANTHROPIC_API_KEY" not in env and "ANTSECRET" not in env.values()
    assert "GITHUB_TOKEN" not in env and "RANDOM_OTHER" not in env
    assert env["FLAGSMITH_CLIENT_KEY"] == "cl-key" and env["FLAGSMITH_SERVER_KEY"] == "sv-key"
    assert env["FLAGSMITH_API_KEY"] == "ad-key" and env["FLAGSMITH_PROJECT_ID"] == "proj-77"
    # the key itself is never written into the config, only a reference to the env var
    assert "NEBSECRET" not in env["OPENCODE_CONFIG_CONTENT"]
    assert "{env:NEBIUS_API_KEY}" in env["OPENCODE_CONFIG_CONTENT"]


def test_claude_env_never_sees_nebius_key():
    env = agents.get_backend("claude").build_env(SECRETS)
    assert "NEBIUS_API_KEY" not in env and "FS_EXPERIMENT_SERVER_KEY" not in env
    assert env["ANTHROPIC_API_KEY"] == "ANTSECRET"


def test_opencode_env_state_dirs_and_isolation_switches(tmp_path):
    env = OpenCodeBackend().build_env(SECRETS, model="m", state_dir=tmp_path / "st")
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        assert pathlib.Path(env[var]).is_dir() and str(tmp_path) in env[var]
    assert env["OPENCODE_DISABLE_CLAUDE_CODE"] == env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "1"
    assert env["OPENCODE_DISABLE_AUTOUPDATE"] == "1"


def test_config_content():
    cfg = build_config("Org/M", {"NEBIUS_BASE_URL": "", "HANDOFF_CONTEXT_LIMIT": "262144"})
    prov = cfg["provider"]["nebius"]
    assert cfg["model"] == "nebius/Org/M"
    assert prov["options"]["baseURL"] == "https://api.tokenfactory.nebius.com/v1/"  # empty var -> default
    assert prov["npm"] == "@ai-sdk/openai-compatible"
    assert prov["models"]["Org/M"]["limit"]["context"] == 262144 and prov["models"]["Org/M"]["tool_call"] is True
    assert build_config("m", {"NEBIUS_BASE_URL": "http://x/v1"})["provider"]["nebius"]["options"]["baseURL"] == "http://x/v1"
    perm = cfg["permission"]
    assert {k for k, v in perm.items() if v == "allow"} == {"bash", "edit", "read", "glob", "grep", "webfetch", "skill"}
    assert "steps" not in json.dumps(cfg)


# ---- selection
def test_agent_selection_precedence_and_validation():
    assert agents.resolve_name(None, {}) == "claude"
    assert agents.resolve_name(None, {"HANDOFF_AGENT": ""}) == "claude"  # unset Actions variable
    assert agents.resolve_name(None, {"HANDOFF_AGENT": "opencode"}) == "opencode"
    assert agents.resolve_name("claude", {"HANDOFF_AGENT": "opencode"}) == "claude"
    with pytest.raises(ValueError):
        agents.resolve_name("nope", {})


def test_cli_rejects_unknown_agent_env(tmp_path):
    r = subprocess.run([sys.executable, "-m", "runner", "--trial-id", "t", "--out-dir", str(tmp_path),
                        "--dry-run"], capture_output=True, text=True, check=False,
                       cwd=workspace.REPO_ROOT, env={**os.environ, "HANDOFF_AGENT": "bogus"})  # fmt: skip
    assert r.returncode == 2 and "unknown agent" in r.stderr


def test_price_cost():
    assert price_cost(1_000_000, 500_000, {}) == 0.0
    assert price_cost(1_000_000, 500_000, {"HANDOFF_PRICE_IN_PER_M": "", "HANDOFF_PRICE_OUT_PER_M": ""}) == 0.0
    env = {"HANDOFF_PRICE_IN_PER_M": "0.4", "HANDOFF_PRICE_OUT_PER_M": "1.8"}
    assert price_cost(1_000_000, 500_000, env) == pytest.approx(0.4 + 0.9)
    assert price_cost(1, 1, {"HANDOFF_PRICE_IN_PER_M": "junk"}) == 0.0
    b = OpenCodeBackend()
    assert b.cost_usd(0.0, 2_000_000, 0, env) == pytest.approx(0.8) and b.cost_usd(0.3, 2_000_000, 0, env) == 0.3


# ---- skill delivery
def test_skill_path_per_backend_and_only_for_variant_b(fixtures, tmp_path):
    kw = {"apps_dir": fixtures["apps_dir"], "skill_dir": fixtures["skill_dir"]}
    assert agents.get_backend("claude").skill_install_dir == ".claude/skills"
    rel = agents.get_backend("opencode").skill_install_dir
    assert rel == ".opencode/skills"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    wa = workspace.prepare_workspace(tmp_path / "a", "node", "prompt", skill_install_dir=rel, **kw)
    wb = workspace.prepare_workspace(tmp_path / "b", "node", "skill", skill_install_dir=rel, **kw)
    assert not (wa / ".opencode").exists() and not (wa / ".claude").exists()
    assert (wb / ".opencode" / "skills" / "flagsmith-ab-test" / "SKILL.md").is_file()
    assert not (wb / ".claude").exists()
    (wb / "new.txt").write_text("x")
    assert "SKILL.md" not in workspace.capture_diff(wb)


# ---- full trial through the real run_agent path with a fake opencode executable
FAKE_BIN = """\
    #!{py}
    import json, os, pathlib, sys
    if "--version" in sys.argv:
        print("9.9.9-fake")
        sys.exit(0)
    instruction = sys.stdin.read()
    skill = pathlib.Path(".opencode/skills/flagsmith-ab-test/SKILL.md").is_file()
    seen = {{"env": sorted(os.environ), "skill": skill, "argv": sys.argv[1:], "instruction": instruction[:40],
            "cfg": json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])["model"]}}
    pathlib.Path("made.txt").write_text("x")
    def sf(i, reason):
        tok = {{"total": 0, "input": 700000, "output": 100000, "reasoning": 0, "cache": {{"write": 0, "read": 0}}}}
        return {{"type": "step_finish", "part": {{"id": f"p{{i}}", "reason": reason, "tokens": tok, "cost": 0}}}}
    print(json.dumps(sf(1, "tool-calls")))
    print(json.dumps({{"type": "text", "part": {{"text": json.dumps(seen)}}}}))
    print(json.dumps(sf(2, "stop")))
"""


def _fake_opencode(tmp_path):
    p = tmp_path / "bin" / "opencode"
    p.parent.mkdir()
    p.write_text(textwrap.dedent(FAKE_BIN.format(py=sys.executable)))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def _trial(tmp_path, fixtures, monkeypatch, variant, env, **kw):
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: (a[3].write_text(json.dumps(PASS_RESULT)), PASS_RESULT)[1])
    out = tmp_path / f"out-{variant}"
    rec = run_trial("trial-9-0", out, FakeFlagsmith(variant), FakeCleaner(), limits=Limits(5, 5_000_000, 60),
                    env=env, agent="opencode", agent_bin=_fake_opencode(tmp_path), **fixtures, **kw)  # fmt: skip
    return rec, out


@pytest.mark.parametrize("variant,skill_present", [("skill", True), ("prompt", False)])
def test_full_trial_with_opencode_backend(tmp_path, fixtures, monkeypatch, variant, skill_present):
    env = {**SECRETS, "HANDOFF_MODEL": "Org/Some-Model", "HANDOFF_PRICE_IN_PER_M": "0.5",
           "HANDOFF_PRICE_OUT_PER_M": "2", "PATH": os.environ["PATH"]}  # fmt: skip
    rec, out = _trial(tmp_path, fixtures, monkeypatch, variant, env)
    assert rec["runner_error"] is False, rec["runner_error_message"]
    assert rec["agent"] == "opencode" and rec["agent_version"] == "9.9.9-fake" and rec["model"] == "Org/Some-Model"
    assert rec["turns"] == 2 and rec["limit_hit"] == "none" and rec["passed"] is True
    assert (rec["input_tokens"], rec["output_tokens"]) == (1_400_000, 200_000)
    assert rec["cost_usd"] == pytest.approx(1.4 * 0.5 + 0.2 * 2)
    # what the agent process actually saw
    evs = [json.loads(ln) for ln in (out / "agent_output.jsonl").read_text().splitlines()]
    seen = json.loads(next(e for e in evs if e["type"] == "text")["part"]["text"])
    assert seen["skill"] is skill_present
    assert seen["cfg"] == "nebius/Org/Some-Model" and "NEBIUS_API_KEY" in seen["env"]
    assert "FS_EXPERIMENT_SERVER_KEY" not in seen["env"] and "ANTHROPIC_API_KEY" not in seen["env"]
    assert seen["instruction"].startswith("Set up a Flagsmith A/B test" if skill_present else "OFFICIAL TEXT")
    # secrets never reach saved artifacts
    saved = (out / "agent_output.jsonl").read_text() + (out / "diff.patch").read_text() + (out / "trial_record.json").read_text()
    assert "NEBSECRET" not in saved and "EXPSECRET" not in saved
    assert "made.txt" in (out / "diff.patch").read_text()


def test_opencode_trial_over_token_limit_is_over_budget(tmp_path, fixtures, monkeypatch):
    env = {**SECRETS, "HANDOFF_MODEL": "m", "PATH": os.environ["PATH"]}
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: (a[3].write_text(json.dumps(PASS_RESULT)), PASS_RESULT)[1])
    rec = run_trial("trial-9-1", tmp_path / "o", FakeFlagsmith("skill"), FakeCleaner(), limits=Limits(5, 100_000, 60),
                    env=env, agent="opencode", agent_bin=_fake_opencode(tmp_path), **fixtures)  # fmt: skip
    assert rec["limit_hit"] == "tokens" and rec["over_budget"] is True and rec["cost_usd"] == 0.0


def test_opencode_requires_model(tmp_path, fixtures):
    fs = FakeFlagsmith("prompt")
    rec = run_trial("trial-9-2", tmp_path / "o", fs, FakeCleaner(), limits=LIMITS, env={"PATH": "/bin"},
                    agent="opencode", agent_bin="/nonexistent", **fixtures)  # fmt: skip
    assert rec["runner_error"] is True and "HANDOFF_MODEL" in rec["runner_error_message"]
    assert fs.exposures == [] and rec["events_sent"] == []  # nothing recorded before the agent could run


def test_default_agent_is_claude_and_record_has_agent_field(tmp_path, fixtures, monkeypatch):
    monkeypatch.setattr(grader_step, "run_grader", lambda *a, **k: (a[3].write_text(json.dumps(PASS_RESULT)), PASS_RESULT)[1])
    rec = run_trial("trial-9-3", tmp_path / "o", FakeFlagsmith("prompt"), FakeCleaner(), limits=LIMITS,
                    fake_agent=True, env={}, **fixtures)  # fmt: skip
    assert rec["agent"] == "claude" and rec["model"] == "claude-sonnet-5-5"
    rec2 = run_trial("trial-9-4", tmp_path / "o2", FakeFlagsmith("prompt"), FakeCleaner(), limits=LIMITS,
                     fake_agent=True, env={"HANDOFF_AGENT": "opencode"}, **fixtures)  # fmt: skip
    assert rec2["agent"] == "opencode"
