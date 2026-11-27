"""Constants and configuration for the runner. No secrets live here."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

STACKS = ("react", "node", "python")
VARIANTS = ("prompt", "skill")

FLAG_NAME_PREFIX = "join_button_"
EVENT_NAME = "join_clicked"
CONTROL_VALUE = "Join"
VARIATION_VALUE = "Join free"
EXPERIMENT_FEATURE = "onboarding_method"  # flag in the experiment project (spec section 14)

EVENT_VERIFIED = "integration_verified"
EVENT_OVER_BUDGET = "over_budget"

WALL_LIMIT_S = 30 * 60
DEFAULT_MODEL = "claude-sonnet-5-5"  # placeholder; real model is frozen in Phase 9 via HANDOFF_MODEL

SKILL_NAME = "flagsmith-ab-test"
SKILL_USER_PROMPT = "Set up a Flagsmith A/B test in this app using the flagsmith-ab-test skill."

# Env vars the agent may see. Everything else is dropped.
SANDBOX_ENV_NAMES = (
    "FS_SANDBOX_CLIENT_KEY",
    "FS_SANDBOX_SERVER_KEY",
    "FS_SANDBOX_ADMIN_KEY",
    "FS_SANDBOX_PROJECT_ID",
    "ANTHROPIC_API_KEY",
)
# CI secret name -> variable name the task brief tells the agent about (brief/TASK_BRIEF.md).
AGENT_ENV_ALIASES = {
    "FS_SANDBOX_CLIENT_KEY": "FLAGSMITH_CLIENT_KEY",
    "FS_SANDBOX_SERVER_KEY": "FLAGSMITH_SERVER_KEY",
    "FS_SANDBOX_ADMIN_KEY": "FLAGSMITH_API_KEY",
    "FS_SANDBOX_PROJECT_ID": "FLAGSMITH_PROJECT_ID",
}
# Plumbing only (no credentials): needed for tools, TLS and the CI proxy to work.
PASSTHROUGH_ENV_NAMES = (
    "PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "SHELL",
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "CURL_CA_BUNDLE",
    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
)  # fmt: skip

# Identical for both variants. "Skill" is required so Variant B can load its skill;
# it is given to Variant A too so the tool set is identical.
AGENT_TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "Skill")

EXPERIMENT_KEY_ENV = "FS_EXPERIMENT_SERVER_KEY"


@dataclass(frozen=True)
class Limits:
    max_turns: int
    max_tokens: int
    wall_s: int = WALL_LIMIT_S

    @classmethod
    def from_env(cls, env=None) -> Limits:
        env = os.environ if env is None else env
        # Defaults are loose placeholders until the Phase 9 pilot freezes real values.
        return cls(
            max_turns=int(env.get("HANDOFF_MAX_TURNS") or 60),
            max_tokens=int(env.get("HANDOFF_MAX_TOKENS") or 5_000_000),
        )


STAGES = ("primary", "replication", "rollout")


def resolve_stage(env, assignment: str = "flagsmith") -> str:
    """Stage of a record: HANDOFF_STAGE (default primary); rollout assignment forces `rollout`."""
    if assignment == "rollout":
        return "rollout"
    stage = (env.get("HANDOFF_STAGE") or "primary").strip().lower()
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r} (expected one of {', '.join(STAGES)})")
    return stage
