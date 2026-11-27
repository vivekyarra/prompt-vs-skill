"""OpenCode backend (sst/opencode, npm `opencode-ai`) talking to Nebius through an OpenAI-compatible API.

Verified against opencode-ai 1.19.6 with a local scripted OpenAI-compatible server (see
docs/flagsmith-sdk-notes.md, section 9):
  opencode run --pure --format json --title <t> -m <provider>/<model>   (prompt read from stdin)
JSON events on stdout, one per line: step_start, tool_use, text, step_finish
  {"type":"step_finish","part":{"reason":"tool-calls"|"stop","tokens":{"total","input","output",
   "reasoning","cache":{"write","read"}},"cost":0}} and {"type":"error","error":{"name","data":{"message"}}}.
`input` EXCLUDES cached tokens and `output` EXCLUDES reasoning tokens (observed), so totals below add them back.
Config is injected through OPENCODE_CONFIG_CONTENT (no files in the workspace). `agent.<name>.steps` did NOT
stop a looping model in the test, so turns are enforced by the runner (count step_finish, kill), like Claude.
Not verified against the real Nebius endpoint (no key available while building).
"""

from __future__ import annotations

import json
import pathlib

from runner.agents.base import AgentBackend, os_environ

PROVIDER_ID = "nebius"
DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
API_KEY_ENV = "NEBIUS_API_KEY"
DEFAULT_CONTEXT = 131072  # default; override per model with HANDOFF_CONTEXT_LIMIT
DEFAULT_OUTPUT = 16384  # default; override per model with HANDOFF_OUTPUT_LIMIT

# Same capability set as the Claude backend (Bash Read Write Edit Glob Grep WebFetch Skill). `edit` covers
# write. Everything else is denied so the tool list is identical in both variants (observed: denied tools
# are not offered to the model).
PERMISSIONS = {
    "bash": "allow", "edit": "allow", "read": "allow", "glob": "allow", "grep": "allow",
    "webfetch": "allow", "skill": "allow",
    "list": "deny", "websearch": "deny", "task": "deny", "todowrite": "deny", "question": "deny",
    "lsp": "deny", "external_directory": "deny", "doom_loop": "deny",
}  # fmt: skip


def _int(env, name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    return int(raw) if raw.isdigit() else default


def build_config(model: str, source: dict) -> dict:
    """opencode config (legacy `provider`/`permission` keys: the ones observed to work on 1.19.6)."""
    base_url = (source.get("NEBIUS_BASE_URL") or "").strip() or DEFAULT_BASE_URL
    return {
        "$schema": "https://opencode.ai/config.json",
        "autoupdate": False,
        "share": "disabled",
        "model": f"{PROVIDER_ID}/{model}",
        "provider": {
            PROVIDER_ID: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Nebius",
                "options": {"baseURL": base_url, "apiKey": "{env:" + API_KEY_ENV + "}"},
                "models": {
                    model: {
                        "name": model,
                        "tool_call": True,
                        "limit": {
                            "context": _int(source, "HANDOFF_CONTEXT_LIMIT", DEFAULT_CONTEXT),
                            "output": _int(source, "HANDOFF_OUTPUT_LIMIT", DEFAULT_OUTPUT),
                        },
                    }
                },
            }
        },
        "permission": dict(PERMISSIONS),
    }


class OpenCodeTally:
    """Usage from opencode `--format json` events. One `step_finish` = one model call = one turn."""

    def __init__(self):
        self.steps: dict[str, dict] = {}
        self.text = ""
        self.error: str | None = None
        self.last_reason: str | None = None
        self.cost = 0.0

    def feed(self, line: str) -> None:
        try:
            ev = json.loads(line)
        except ValueError:
            return
        if not isinstance(ev, dict):
            return
        kind, part = ev.get("type"), ev.get("part")
        part = part if isinstance(part, dict) else {}
        if kind == "step_finish":
            self.steps[part.get("id") or f"anon{len(self.steps)}"] = part
            self.last_reason = part.get("reason")
        elif kind == "text" and part.get("text"):
            self.text = str(part["text"])
        elif kind == "error":
            err = ev.get("error") if isinstance(ev.get("error"), dict) else {}
            data = err.get("data") if isinstance(err.get("data"), dict) else {}
            self.error = str(data.get("message") or err.get("name") or "error")

    def _sum(self) -> tuple[int, int, int, float]:
        i = o = cr = 0
        cost = 0.0
        for p in self.steps.values():
            t = p.get("tokens") if isinstance(p.get("tokens"), dict) else {}
            c = t.get("cache") if isinstance(t.get("cache"), dict) else {}
            read, write = c.get("read") or 0, c.get("write") or 0
            i += (t.get("input") or 0) + read + write
            o += (t.get("output") or 0) + (t.get("reasoning") or 0)
            cr += read
            cost += float(p.get("cost") or 0.0)
        return i, o, cr, cost

    def live(self) -> tuple[int, int]:
        i, o, _, _ = self._sum()
        return len(self.steps), i + o

    def fill(self, r) -> bool:
        r.input_tokens, r.output_tokens, r.cache_read_tokens, r.cost_usd = self._sum()
        r.final_text = self.text
        if self.error:
            r.result_subtype = "error"
            r.final_text = r.final_text or self.error
        elif self.steps:
            r.result_subtype = "success" if self.last_reason != "tool-calls" else "incomplete"
        return bool(self.steps or self.error)


class OpenCodeBackend(AgentBackend):
    name = "opencode"
    default_bin = "opencode"
    model_secret_names = (API_KEY_ENV,)
    skill_install_dir = ".opencode/skills"

    def build_command(self, model: str, max_turns: int) -> list[str]:
        # --title stops opencode making a separate title-generation model call (it would spend tokens that
        # never appear in the event stream). --pure: no external plugins (and no npm install in the workspace).
        # max_turns is deliberately not passed: enforced by the runner, identically to the Claude backend.
        return [
            self.binary, "run", "--pure", "--format", "json", "--title", "handoff",
            "-m", f"{PROVIDER_ID}/{model}",
        ]  # fmt: skip

    def build_env(self, source: dict | None = None, *, model: str = "", state_dir=None) -> dict:
        source = os_environ(source)
        env = self.base_env(source, (API_KEY_ENV,))
        env.update(
            OPENCODE_CONFIG_CONTENT=json.dumps(build_config(model, source)),
            OPENCODE_DISABLE_AUTOUPDATE="1",
            OPENCODE_DISABLE_MODELS_FETCH="1",
            OPENCODE_DISABLE_CLAUDE_CODE="1",  # no ~/.claude prompt/skills leaking into either variant
            OPENCODE_DISABLE_EXTERNAL_SKILLS="1",
        )
        if state_dir is not None:  # per-trial config/data/cache: no global opencode config or sessions
            state = pathlib.Path(state_dir)
            for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                             ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):  # fmt: skip
                (state / sub).mkdir(parents=True, exist_ok=True)
                env[var] = str(state / sub)
        return env

    def make_tally(self):
        return OpenCodeTally()
