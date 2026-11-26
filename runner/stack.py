"""Deterministic stack selection (spec section 13 step 1)."""

from __future__ import annotations

import hashlib

from runner.config import STACKS


def pick_stack(trial_id: str) -> str:
    """Uniform over STACKS, a pure function of the trial id (SHA-256, first 8 bytes mod 3)."""
    digest = hashlib.sha256(trial_id.encode("utf-8")).digest()
    return STACKS[int.from_bytes(digest[:8], "big") % len(STACKS)]
