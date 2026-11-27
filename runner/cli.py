"""python -m runner --trial-id <id> --out-dir <path> [--dry-run] [--scripted-agent] [--skip-grader]
[--assign flagsmith|local|rollout]   (local = PILOT ONLY: variant from a hash of the trial id, no Flagsmith;
rollout = plain flag read after the experiment ended, no events, stage forced to `rollout`)"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from runner.agents import AGENT_CHOICES, resolve_name
from runner.config import VARIANTS, resolve_stage
from runner.flags import (
    ExposureResult,
    NoopCleaner,
    RolloutFlagsmithClient,
    SdkFlagsmithClient,
    cleaner_from_env,
)
from runner.stack import pick_stack
from runner.trial import new_record, run_trial


class OfflineFlagsmith:
    """Dry-run stand-in: deterministic variant from the trial id, events recorded not sent."""

    def __init__(self, out_dir: pathlib.Path):
        self.out_dir, self.events = out_dir, []

    def get_exposure(self, trial_id: str, stack: str) -> ExposureResult:
        import hashlib

        v = VARIANTS[hashlib.sha256(b"variant:" + trial_id.encode()).digest()[0] % 2]
        return ExposureResult(v, True, v, None)

    def send_event(self, event: str, trial_id: str, stack: str) -> None:
        self.events.append({"event": event, "identifier": trial_id, "stack": stack})

    def flush(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "dry_run_events.json").write_text(json.dumps(self.events, indent=2) + "\n")

    def close(self) -> None:
        pass


class LocalAssignment:
    """PILOT ONLY. Variant = deterministic ~50/50 split from SHA-256("local-variant:" + trial_id).
    Balanced in expectation (not exactly per batch). No Flagsmith calls; events are discarded."""

    def get_exposure(self, trial_id: str, stack: str) -> ExposureResult:
        import hashlib

        v = VARIANTS[hashlib.sha256(b"local-variant:" + trial_id.encode()).digest()[0] % 2]
        return ExposureResult(v, True, v, None)

    def send_event(self, event: str, trial_id: str, stack: str) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def resolve_assign(arg: str | None, env) -> str:
    """Pick the assignment mode and refuse `local` for the real (production) experiment."""
    mode = (arg or env.get("HANDOFF_ASSIGN") or "flagsmith").strip().lower()
    if mode not in ("flagsmith", "local", "rollout"):
        raise ValueError(f"unknown assignment mode {mode!r} (expected flagsmith, local or rollout)")
    if mode == "local" and env.get("HANDOFF_ENVIRONMENT", "").strip().lower() == "production":
        raise ValueError("--assign local is a pilot mode and is refused when HANDOFF_ENVIRONMENT=production")
    return mode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="runner", description="Run one trial end to end.")
    ap.add_argument("--trial-id", required=True)
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="no credentials needed: scripted agent, offline Flagsmith, no cleanup")  # fmt: skip
    ap.add_argument("--scripted-agent", action="store_true", help="stub agent (makes no changes)")
    ap.add_argument("--scripted-agent-apply-reference", action="store_true",
                    help="scripted agent that copies the reference integration (CI smoke of runner+grader)")  # fmt: skip
    ap.add_argument("--skip-grader", action="store_true", help="do not run the grader (CI smoke only)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--agent", choices=AGENT_CHOICES, default=None,
                    help="agent backend (default: env HANDOFF_AGENT, else claude)")  # fmt: skip
    ap.add_argument("--assign", choices=("flagsmith", "local", "rollout"), default=None,
                    help="variant assignment (default: env HANDOFF_ASSIGN, else flagsmith); "
                    "local = pilot only, never for the real experiment; rollout = plain flag read, no events")  # fmt: skip
    ap.add_argument("--print-stack", action="store_true", help="print the stack for this id and exit")
    a = ap.parse_args(argv)
    if a.print_stack:
        print(pick_stack(a.trial_id))
        return 0
    try:
        agent_name = resolve_name(a.agent, os.environ)
    except ValueError as e:
        print(f"runner_error: {e}", file=sys.stderr)
        return 2
    try:
        assign = resolve_assign(a.assign, os.environ)
    except ValueError as e:
        print(f"runner_error: {e}", file=sys.stderr)
        return 2
    if assign == "local":
        print("WARNING: LOCAL ASSIGNMENT PILOT - no Flagsmith experiment, no events; not experiment data",
              file=sys.stderr)
    try:
        resolve_stage(os.environ, assign)
    except ValueError as e:
        print(f"runner_error: {e}", file=sys.stderr)
        return 2
    if assign == "rollout":
        print("NOTE: ROLLOUT MODE - plain flag read, no events sent; stage=rollout; not experiment data",
              file=sys.stderr)
    if assign == "rollout" and not a.dry_run:
        try:
            fs, cleaner = RolloutFlagsmithClient(), cleaner_from_env()
        except Exception as e:  # noqa: BLE001
            print(f"runner_error: cannot create Flagsmith client: {e}", file=sys.stderr)
            a.out_dir.mkdir(parents=True, exist_ok=True)
            rec = new_record(a.trial_id, a.model or "unknown", agent_name)
            rec.update(assignment=assign, stage="rollout", runner_error=True,
                       runner_error_message=f"flagsmith client: {e}")  # fmt: skip
            (a.out_dir / "trial_record.json").write_text(json.dumps(rec, indent=2) + "\n")
            return 1
    elif assign in ("local", "rollout"):
        fs, cleaner = LocalAssignment(), (NoopCleaner() if a.dry_run else cleaner_from_env())
    elif a.dry_run:
        fs, cleaner = OfflineFlagsmith(a.out_dir), NoopCleaner()
    else:
        try:
            fs, cleaner = SdkFlagsmithClient(), cleaner_from_env()
        except Exception as e:  # noqa: BLE001 - e.g. missing key or SDK; before exposure, no agent run
            print(f"runner_error: cannot create Flagsmith client: {e}", file=sys.stderr)
            a.out_dir.mkdir(parents=True, exist_ok=True)
            rec = new_record(a.trial_id, a.model or "unknown", agent_name)
            rec["assignment"] = assign
            rec["stage"] = resolve_stage(os.environ, assign)
            rec.update(runner_error=True, runner_error_message=f"flagsmith client: {e}")
            (a.out_dir / "trial_record.json").write_text(json.dumps(rec, indent=2) + "\n")
            return 1
    rec = run_trial(
        a.trial_id, a.out_dir, fs, cleaner, model=a.model, scripted_agent=a.scripted_agent,
        scripted_apply_reference=a.scripted_agent_apply_reference,
        skip_grader=a.skip_grader, dry_run=a.dry_run, agent=agent_name, assignment=assign,
    )  # fmt: skip
    print(json.dumps({k: rec[k] for k in ("trial_id", "variant", "stack", "passed", "limit_hit",
                                          "events_sent", "runner_error")}))  # fmt: skip
    print("TRIAL_RECORD_JSON:")
    print(json.dumps(rec, indent=2))
    return 1 if rec["runner_error"] else 0
