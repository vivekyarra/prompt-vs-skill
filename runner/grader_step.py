"""Runs the grader (separate package, built elsewhere) as a subprocess (spec step 7)."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from runner.agent import build_agent_env
from runner.config import CONTROL_VALUE, EVENT_NAME, REPO_ROOT, VARIATION_VALUE

CHECK_IDS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")


class GraderError(RuntimeError):
    pass


def run_grader(
    app_dir: pathlib.Path,
    stack: str,
    flag_name: str,
    out_path: pathlib.Path,
    timeout_s: int = 900,
    env_source: dict | None = None,
) -> dict:
    """Invoke `python -m grader ...`; return parsed result.json. The grader executes the agent's
    code, so it gets the same scrubbed environment as the agent (never the experiment key)."""
    cmd = [
        sys.executable, "-m", "grader",
        "--app-dir", str(app_dir), "--stack", stack, "--flag", flag_name,
        "--event", EVENT_NAME, "--variant-values", f"{CONTROL_VALUE},{VARIATION_VALUE}",
        "--out", str(out_path), "--reclaim-port",
    ]  # fmt: skip
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, env=build_agent_env(env_source),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired as e:
        raise GraderError(f"grader timed out after {timeout_s}s") from e
    if not out_path.is_file():
        raise GraderError(f"grader produced no result.json (exit {proc.returncode}): {proc.stderr[-500:]}")
    try:
        return json.loads(out_path.read_text(encoding="utf-8", errors="replace"))
    except ValueError as e:
        raise GraderError(f"unreadable grader result: {e}") from e


def summarize(result: dict) -> tuple[dict, list[str], bool]:
    """-> (checks {C1..C7: bool}, failure_reasons, passed). Passed = grader's own `passed`."""
    raw = result.get("checks") or {}
    checks, reasons = {}, []
    for cid in CHECK_IDS:
        c = raw.get(cid)
        ok = bool(c.get("passed")) if isinstance(c, dict) else bool(c)
        checks[cid] = ok
        if not ok:
            why = c.get("reason") if isinstance(c, dict) else None
            reasons.append(f"{cid}: {why or 'failed or missing'}")
    return checks, reasons, bool(result.get("passed"))


def skipped_result() -> dict:
    """Used only with --skip-grader (CI smoke tests): everything marked failed, loudly."""
    return {
        "passed": False,
        "checks": {c: {"passed": False, "reason": "grader skipped"} for c in CHECK_IDS},
    }
