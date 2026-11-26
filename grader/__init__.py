"""Handoff grader: judges whether an app's Flagsmith experiment is correctly wired (spec section 10)."""

from __future__ import annotations

import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent


def grader_version() -> str:
    """Commit SHA of the repo containing the grader ("unknown" outside a checkout)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else "unknown"
    except Exception:
        return "unknown"
