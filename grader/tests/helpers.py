"""Helpers for the grader self-tests."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
FLAG = "join_button_selftest"
STACKS = ("react", "node", "python")


def run_grader(app_dir, stack, out, mode="emulator", fast=True) -> dict:
    cmd = [
        sys.executable, "-m", "grader", "--app-dir", str(app_dir), "--stack", stack, "--flag", FLAG,
        "--event", "join_clicked", "--variant-values", "Join,Join free", "--out", str(out), "--mode", mode,
    ]  # fmt: skip
    if fast:
        cmd += ["--load-wait", "1", "--click-wait", "2"]
    subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=900, check=False)
    return json.loads(pathlib.Path(out).read_text())


def failed(result: dict, include_c7=False) -> set:
    return {c for c, v in result["checks"].items() if not v["passed"] and (include_c7 or c != "C7")}
