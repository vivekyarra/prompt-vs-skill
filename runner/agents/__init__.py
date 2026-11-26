"""Pluggable agent backends. Select with env HANDOFF_AGENT or `--agent` (default: claude)."""

from __future__ import annotations

from runner.agents.base import AgentBackend
from runner.agents.claude import ClaudeBackend
from runner.agents.opencode import OpenCodeBackend

BACKENDS: dict[str, type[AgentBackend]] = {"claude": ClaudeBackend, "opencode": OpenCodeBackend}
AGENT_CHOICES = tuple(BACKENDS)
DEFAULT_AGENT = "claude"


def resolve_name(cli_value: str | None = None, env: dict | None = None) -> str:
    """--agent beats HANDOFF_AGENT beats the default; empty values (unset Actions vars) are ignored."""
    name = (cli_value or (env or {}).get("HANDOFF_AGENT") or DEFAULT_AGENT).strip().lower()
    if name not in BACKENDS:
        raise ValueError(f"unknown agent {name!r}; choose one of {', '.join(AGENT_CHOICES)}")
    return name


def get_backend(name: str, binary: str | None = None) -> AgentBackend:
    return BACKENDS[resolve_name(name)](binary)
