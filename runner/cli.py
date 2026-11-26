"""python -m runner --trial-id <id> --out-dir <path> [--dry-run] [--fake-agent] [--skip-grader]"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from runner.config import VARIANTS
from runner.flags import ExposureResult, NoopCleaner, SdkFlagsmithClient, cleaner_from_env
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="runner", description="Run one trial end to end.")
    ap.add_argument("--trial-id", required=True)
    ap.add_argument("--out-dir", required=True, type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="no credentials needed: fake agent, offline Flagsmith, no cleanup")  # fmt: skip
    ap.add_argument("--fake-agent", action="store_true", help="stub agent (makes no changes)")
    ap.add_argument("--fake-agent-apply-reference", action="store_true",
                    help="fake agent that copies the reference integration (CI smoke of runner+grader)")  # fmt: skip
    ap.add_argument("--skip-grader", action="store_true", help="do not run the grader (CI smoke only)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--print-stack", action="store_true", help="print the stack for this id and exit")
    a = ap.parse_args(argv)
    if a.print_stack:
        print(pick_stack(a.trial_id))
        return 0
    if a.dry_run:
        fs, cleaner = OfflineFlagsmith(a.out_dir), NoopCleaner()
    else:
        try:
            fs, cleaner = SdkFlagsmithClient(), cleaner_from_env()
        except Exception as e:  # noqa: BLE001 - e.g. missing key or SDK; before exposure, no agent run
            print(f"runner_error: cannot create Flagsmith client: {e}", file=sys.stderr)
            a.out_dir.mkdir(parents=True, exist_ok=True)
            rec = new_record(a.trial_id, a.model or "unknown")
            rec.update(runner_error=True, runner_error_message=f"flagsmith client: {e}")
            (a.out_dir / "trial_record.json").write_text(json.dumps(rec, indent=2) + "\n")
            return 1
    rec = run_trial(
        a.trial_id, a.out_dir, fs, cleaner, model=a.model, fake_agent=a.fake_agent,
        fake_apply_reference=a.fake_agent_apply_reference,
        skip_grader=a.skip_grader, dry_run=a.dry_run,
    )  # fmt: skip
    print(json.dumps({k: rec[k] for k in ("trial_id", "variant", "stack", "passed", "limit_hit",
                                          "events_sent", "runner_error")}))  # fmt: skip
    return 1 if rec["runner_error"] else 0
