"""The small interface every agent backend implements."""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod

from runner.config import (
    AGENT_ENV_ALIASES,
    PASSTHROUGH_ENV_NAMES,
    SANDBOX_ENV_NAMES,
)

PRICE_IN_ENV = "HANDOFF_PRICE_IN_PER_M"
PRICE_OUT_ENV = "HANDOFF_PRICE_OUT_PER_M"


def _price(env, name: str) -> float | None:
    raw = (env.get(name) or "").strip()  # empty Actions variables arrive as ""
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def price_cost(input_tokens: int, output_tokens: int, env: dict) -> float:
    """USD from per-million prices in HANDOFF_PRICE_IN_PER_M / HANDOFF_PRICE_OUT_PER_M, else 0.0.
    Every input token (cache reads included) is billed at the input price: an upper bound."""
    p_in, p_out = _price(env, PRICE_IN_ENV), _price(env, PRICE_OUT_ENV)
    if p_in is None and p_out is None:
        return 0.0
    return (input_tokens * (p_in or 0.0) + output_tokens * (p_out or 0.0)) / 1_000_000


class AgentBackend(ABC):
    """One headless coding-agent CLI. The runner stays identical for every backend: it feeds the
    instruction on stdin, reads stdout lines, and kills the process when a limit is exceeded."""

    name: str = ""
    default_bin: str = ""
    # Extra names (beyond the sandbox credentials) whose values must be scrubbed from saved output.
    model_secret_names: tuple[str, ...] = ()
    # Directory, relative to the workspace root, where this agent discovers project skills.
    skill_install_dir: str = ""

    def __init__(self, binary: str | None = None):
        self.binary = binary or self.default_bin

    @abstractmethod
    def build_command(self, model: str, max_turns: int) -> list[str]:
        """argv for a headless run; the instruction arrives on stdin."""

    @abstractmethod
    def build_env(self, source: dict | None = None, *, model: str = "", state_dir=None) -> dict:
        """Allowlisted environment for the agent process (never the experiment key)."""

    @abstractmethod
    def make_tally(self):
        """Fresh usage parser with feed(line), live() -> (turns, tokens), fill(AgentResult) -> bool."""

    def version(self) -> str:
        try:
            r = subprocess.run([self.binary, "--version"], capture_output=True, text=True, timeout=30, check=False)
            return r.stdout.strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            return "unknown"

    def cost_usd(self, reported: float, input_tokens: int, output_tokens: int, env: dict) -> float:
        """CLI-reported cost wins; otherwise price-based; otherwise 0.0."""
        return reported or price_cost(input_tokens, output_tokens, env)

    def secrets(self, env: dict) -> list[str]:
        names = SANDBOX_ENV_NAMES + self.model_secret_names
        return [env.get(n, "") for n in names]

    @staticmethod
    def base_env(source: dict, extra_names: tuple[str, ...] = ()) -> dict:
        """Allowlist: sandbox credentials (+ `extra_names`) and plumbing, with the FS_SANDBOX_* ->
        FLAGSMITH_* aliases the task brief refers to. Never anything else."""
        creds = tuple(n for n in SANDBOX_ENV_NAMES if n != "ANTHROPIC_API_KEY")
        env = {k: source[k] for k in creds + extra_names + PASSTHROUGH_ENV_NAMES if source.get(k)}
        for src_name, dst_name in AGENT_ENV_ALIASES.items():
            if env.get(src_name):
                env[dst_name] = env[src_name]
        return env


def os_environ(source: dict | None) -> dict:
    return os.environ if source is None else source
