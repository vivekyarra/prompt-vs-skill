"""Claude Code backend: the original runner behaviour, unchanged (see runner/agent.py)."""

from __future__ import annotations

from runner import agent as agent_mod
from runner.agents.base import AgentBackend, os_environ


class ClaudeBackend(AgentBackend):
    name = "claude"
    default_bin = "claude"
    model_secret_names = ("ANTHROPIC_API_KEY",)
    skill_install_dir = ".claude/skills"

    def build_command(self, model: str, max_turns: int) -> list[str]:
        return agent_mod.build_command(model, max_turns, self.binary)

    def build_env(self, source: dict | None = None, *, model: str = "", state_dir=None) -> dict:
        return agent_mod.build_agent_env(os_environ(source))

    def make_tally(self):
        return agent_mod._Tally()
