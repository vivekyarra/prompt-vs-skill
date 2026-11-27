"""One complete trial, end to end (spec section 13)."""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import shutil
import tempfile
import time
from datetime import datetime, timezone

from runner import agent as agent_mod
from runner import agents as agents_mod
from runner import grader_step, workspace
from runner.config import (
    DEFAULT_MODEL,
    EXPERIMENT_KEY_ENV,
    REPO_ROOT,
    SKILL_NAME,
    Limits,
    resolve_skill_dir,
    resolve_stage,
)
from runner.events import decide_events, send_events
from runner.flags import FlagsmithClient, NoopCleaner, SandboxCleaner
from runner.skill_usage import count_skill_calls
from runner.stack import pick_stack

RECORD_FIELDS = (
    "trial_id", "timestamp_utc", "variant", "stack", "model", "agent", "agent_version", "prompt_sha256",
    "skill_sha", "skill_dir", "grader_sha", "brief_sha256", "turns", "input_tokens", "output_tokens", "cost_usd",
    "duration_s", "over_budget", "limit_hit", "checks", "failure_reasons", "passed", "events_sent",
    "agent_diff_path", "runner_error", "skill_tool_calls", "skill_loaded", "flag_exists_at_cleanup",
    "flag_created_during_trial",
)  # fmt: skip


def new_record(trial_id: str, model: str, agent: str = "claude") -> dict:
    return {
        "trial_id": trial_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "variant": None,
        "stack": pick_stack(trial_id),
        "model": model,
        "agent": agent,
        "agent_version": None,
        "prompt_sha256": None,
        "skill_sha": None,
        "skill_dir": None,
        "grader_sha": None,
        "brief_sha256": None,
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "duration_s": 0,
        "over_budget": False,
        "limit_hit": "none",
        "checks": {},
        "failure_reasons": [],
        "passed": False,
        "events_sent": [],
        "agent_diff_path": "diff.patch",
        "runner_error": False,
        # extras beyond the spec
        "runner_error_message": None,
        "events_flush_confirmed": None,
        "cache_read_tokens": 0,
        "agent_exit_code": None,
        "agent_result_subtype": None,
        "flag_name": None,
        "cleanup_status": None,
        "skill_tool_calls": 0,
        "skill_loaded": False,
        "flag_exists_at_cleanup": None,
        "flag_created_during_trial": None,
        "dry_run": False,
        "fake_agent": False,
        "grader_skipped": False,
        "assignment": "flagsmith",
        "stage": "primary",
    }


def flag_created_during(created_date, started: datetime) -> bool | None:
    """True if created_date >= trial start, False if earlier, None if absent/unparseable."""
    if not isinstance(created_date, str) or not created_date:
        return None
    try:
        dt = datetime.fromisoformat(created_date.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= started


def _scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def _write_json(path: pathlib.Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def run_trial(
    trial_id: str,
    out_dir: pathlib.Path,
    flagsmith: FlagsmithClient,
    cleaner: SandboxCleaner | None = None,
    limits: Limits | None = None,
    model: str | None = None,
    fake_agent: bool = False,
    fake_apply_reference: bool = False,
    skip_grader: bool = False,
    dry_run: bool = False,
    env: dict | None = None,
    apps_dir: pathlib.Path | None = None,
    skill_dir: pathlib.Path | None = None,
    prompt_path: pathlib.Path | None = None,
    brief_path: pathlib.Path | None = None,
    grader_dir: pathlib.Path | None = None,
    claude_bin: str = "claude",
    agent: str | None = None,
    agent_bin: str | None = None,
    sleep=time.sleep,
    assignment: str = "flagsmith",
) -> dict:
    """Run one trial and return its record (also written to out_dir/trial_record.json).
    Never raises for trial-level problems: those become runner_error."""
    env = dict(os.environ) if env is None else env
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    limits = limits or Limits.from_env(env)
    agent_name = agents_mod.resolve_name(agent, env)
    backend = agents_mod.get_backend(agent_name, agent_bin or (claude_bin if agent_name == "claude" else None))
    # Only the Claude backend has a usable built-in default model; other agents need HANDOFF_MODEL.
    model = model or env.get("HANDOFF_MODEL") or (DEFAULT_MODEL if agent_name == "claude" else "")
    cleaner = cleaner or NoopCleaner()
    grader_dir = grader_dir or REPO_ROOT / "grader"
    rec = new_record(trial_id, model or "unset", agent_name)
    started = datetime.now(timezone.utc)
    rec.update(dry_run=dry_run, fake_agent=fake_agent or dry_run, grader_skipped=skip_grader)
    rec["assignment"] = assignment
    _env = env if env is not None else os.environ
    rec["environment"] = (_env.get("HANDOFF_ENVIRONMENT") or "unspecified").strip().lower()
    rec["repo_sha"] = _env.get("GITHUB_SHA") or ""
    rec["max_turns"], rec["max_tokens"] = limits.max_turns, limits.max_tokens
    stack = rec["stack"]
    flag_name = rec["flag_name"] = workspace.flag_name_for(trial_id)
    secrets = backend.secrets(env) + [env.get(EXPERIMENT_KEY_ENV, "")]
    work_dir = pathlib.Path(tempfile.mkdtemp(prefix="handoff-trial-"))
    reached_agent = False
    try:
        rec["stage"] = resolve_stage(env, assignment)
        if skill_dir is None:
            rec["skill_dir"] = resolve_skill_dir(env)
            skill_dir = REPO_ROOT / rec["skill_dir"]
        else:
            rec["skill_dir"] = str(skill_dir)
        if not model and not (fake_agent or dry_run):
            raise RuntimeError(f"no model: set HANDOFF_MODEL (required for agent {agent_name})")
        # Step 2: exposure. Only infrastructure failures before this point may be retried.
        exposure = None
        for attempt in range(3):
            try:
                exposure = flagsmith.get_exposure(trial_id, stack)
                break
            except Exception:
                if attempt == 2:
                    raise
                sleep(2 * (attempt + 1))
        variant = rec["variant"] = exposure.variant

        # Steps 3-4: workspace and variant delivery.
        prompt_path = prompt_path or REPO_ROOT / "prompt" / "OFFICIAL_PROMPT.md"
        brief_path = brief_path or REPO_ROOT / "brief" / "TASK_BRIEF.md"
        prompt_text, rec["prompt_sha256"] = workspace.load_official_prompt(prompt_path)
        brief, rec["brief_sha256"] = workspace.load_brief(brief_path, trial_id)
        instruction = workspace.build_instruction(variant, prompt_text, brief)
        ws = workspace.prepare_workspace(
            work_dir, stack, variant, apps_dir, skill_dir, skill_install_dir=backend.skill_install_dir
        )
        rec["skill_sha"] = workspace.tree_sha(skill_dir)
        rec["grader_sha"] = workspace.tree_sha(grader_dir)

        # Steps 5-6: agent. From here on a trial is never retried.
        reached_agent = True
        if fake_agent or dry_run:
            rec["agent_version"] = "fake-agent"
            res = agent_mod.fake_agent_result()
            if fake_apply_reference:  # CI smoke: stand in for a perfect agent
                ref = (apps_dir or REPO_ROOT / "apps") / "reference" / stack
                shutil.copytree(ref, ws, dirs_exist_ok=True, ignore=shutil.ignore_patterns(
                    "node_modules", "dist", "__pycache__", ".venv", ".pytest_cache"))  # fmt: skip
        else:
            rec["agent_version"] = backend.version()
            cmd = backend.build_command(model, limits.max_turns)
            agent_env = backend.build_env(env, model=model, state_dir=work_dir / "agent-state")
            res = agent_mod.run_agent(cmd, instruction, ws, agent_env, limits, tally=backend.make_tally())
            res.cost_usd = backend.cost_usd(res.cost_usd, res.input_tokens, res.output_tokens, env)
        rec.update(
            turns=res.turns,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            cache_read_tokens=res.cache_read_tokens,
            cost_usd=round(res.cost_usd, 6),
            duration_s=round(res.duration_s, 1),
            over_budget=res.over_budget,
            limit_hit=res.limit_hit,
            agent_exit_code=res.exit_code,
            agent_result_subtype=res.result_subtype,
        )
        kept = [ln for ln in res.raw_lines if '"type":"stream_event"' not in ln.replace(" ", "")]
        with contextlib.suppress(Exception):  # record-only
            rec["skill_tool_calls"], rec["skill_loaded"] = count_skill_calls(res.raw_lines, SKILL_NAME)
        (out_dir / "agent_output.jsonl").write_text(_scrub("".join(kept), secrets), encoding="utf-8")
        (out_dir / "diff.patch").write_text(_scrub(workspace.capture_diff(ws), secrets), encoding="utf-8")

        # An agent that died on a provider/CLI error is an infrastructure fault, not a failed
        # integration: record it as a runner error (no verdict, no conversion event).
        real_agent = not (fake_agent or dry_run)
        if res.limit_hit == "none" and (
            (res.result_subtype or "") in ("error", "error_during_execution")
            or (real_agent and res.turns == 0)  # a CLI crash may emit no error event at all
        ):
            raise RuntimeError(f"agent infrastructure error: {(res.final_text or 'no turns ran')[:200]}")

        # Step 7: grader.
        grader_out = out_dir / "grader_result.json"
        if skip_grader:
            gres = grader_step.skipped_result()
            _write_json(grader_out, gres)
        else:
            gres = grader_step.run_grader(ws, stack, flag_name, grader_out, env_source=env)
        rec["checks"], rec["failure_reasons"], rec["passed"] = grader_step.summarize(gres)

        # Step 8: events (dry-run clients record instead of sending).
        events = decide_events(rec["passed"], rec["limit_hit"], runner_error=False)
        sent, confirmed = send_events(flagsmith, events, trial_id, stack)
        rec["events_sent"], rec["events_flush_confirmed"] = sent, confirmed
        if assignment in ("local", "rollout"):  # nothing reaches Flagsmith; log what would have been sent
            rec["events_sent"], rec["events_would_send"] = [], list(sent)
        if not confirmed:
            raise RuntimeError("Flagsmith event flush could not be confirmed")
    except Exception as e:  # noqa: BLE001 - runner crash: keep the record, send no conversion event
        rec["runner_error"] = True
        rec["runner_error_message"] = _scrub(f"{type(e).__name__}: {e}", secrets)
        rec["reached_agent_step"] = reached_agent
        if rec["events_flush_confirmed"] is False:
            rec["events_sent"] = []
    finally:
        # Step 11: sandbox-only cleanup; best effort and never the experiment project.
        with contextlib.suppress(Exception):  # record-only, read-only; never affects cleanup_status
            info = getattr(cleaner, "inspect_flag", lambda _n: None)(flag_name)
            if isinstance(info, dict) and isinstance(info.get("exists"), bool):
                rec["flag_exists_at_cleanup"] = info["exists"]
                if info["exists"]:
                    rec["flag_created_during_trial"] = flag_created_during(info.get("created_date"), started)
        try:
            rec["cleanup_status"] = cleaner.delete_flag(flag_name)
        except Exception as e:  # noqa: BLE001
            rec["cleanup_status"] = f"error: {type(e).__name__}: {e}"
        with contextlib.suppress(Exception):
            flagsmith.close()
        shutil.rmtree(work_dir, ignore_errors=True)
        _write_json(out_dir / "trial_record.json", rec)
    return rec
