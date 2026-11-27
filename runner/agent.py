"""Headless agent launch (Claude Code CLI) with limit enforcement (spec section 13 steps 5-6).

CLI flags verified from `claude --help` (Claude Code 2.1.332) and a live call:
  -p/--print, --output-format stream-json (needs --verbose), --model, --tools, --allowedTools,
  --permission-mode dontAsk, --setting-sources, --no-session-persistence.
`--max-turns` is NOT listed in `claude --help` for this version but the CLI accepted it (an unknown
flag errors); that it actually stops the session at N turns is not relied on, so the runner also
enforces turns itself by killing the process.
stream-json lines: {"type":"assistant","message":{"id","usage":{input_tokens,output_tokens,
cache_creation_input_tokens,cache_read_input_tokens}}} (repeated per content block, same id) and a
final {"type":"result","subtype","num_turns","total_cost_usd","usage":{...},"is_error"}.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field

from runner.config import (
    AGENT_ENV_ALIASES,
    AGENT_TOOLS,
    PASSTHROUGH_ENV_NAMES,
    SANDBOX_ENV_NAMES,
    Limits,
)


@dataclass
class AgentResult:
    turns: int = 0
    input_tokens: int = 0  # input + cache creation + cache read
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    limit_hit: str = "none"  # none | turns | tokens | time
    exit_code: int | None = None
    result_subtype: str | None = None
    final_text: str = ""
    raw_lines: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def over_budget(self) -> bool:
        return self.limit_hit != "none"


def build_agent_env(source: dict | None = None) -> dict:
    """Allowlist environment for the agent: sandbox creds + plumbing only. Never anything else
    (in particular never FS_EXPERIMENT_SERVER_KEY)."""
    source = os.environ if source is None else source
    names = SANDBOX_ENV_NAMES + PASSTHROUGH_ENV_NAMES
    env = {k: source[k] for k in names if source.get(k)}
    # The task brief names the credentials the agent sees (FLAGSMITH_*); map the CI secret names to them.
    for src_name, dst_name in AGENT_ENV_ALIASES.items():
        if env.get(src_name):
            env[dst_name] = env[src_name]
    return env


def build_command(model: str, max_turns: int, claude_bin: str = "claude") -> list[str]:
    tools = ",".join(AGENT_TOOLS)
    return [
        claude_bin, "-p",
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        "--max-turns", str(max_turns),
        "--tools", tools,
        "--allowedTools", tools,
        "--permission-mode", "dontAsk",
        "--setting-sources", "project",
        "--no-session-persistence",
    ]  # fmt: skip


def evaluate_limits(turns: int, total_tokens: int, elapsed_s: float, limits: Limits) -> str:
    """First exceeded limit, checked in the order turns, tokens, time; else 'none'."""
    if turns > limits.max_turns:
        return "turns"
    if total_tokens > limits.max_tokens:
        return "tokens"
    if elapsed_s > limits.wall_s:
        return "time"
    return "none"


class _Tally:
    """Accumulates usage from stream-json events; last usage per message id wins."""

    def __init__(self):
        self.msgs: dict[str, dict] = {}
        self.result: dict | None = None
        self.text = ""

    def feed(self, line: str) -> None:
        try:
            ev = json.loads(line)
        except ValueError:
            return
        if not isinstance(ev, dict):
            return
        if ev.get("type") == "assistant" and isinstance(ev.get("message"), dict):
            m = ev["message"]
            self.msgs[m.get("id") or f"anon{len(self.msgs)}"] = m.get("usage") or {}
        elif ev.get("type") == "result":
            self.result = ev
            self.text = str(ev.get("result") or "")

    @staticmethod
    def _sum(usages) -> tuple[int, int, int]:
        i = o = cr = 0
        for u in usages:
            cread = u.get("cache_read_input_tokens") or 0
            i += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + cread
            o += u.get("output_tokens") or 0
            cr += cread
        return i, o, cr

    def live(self) -> tuple[int, int]:
        i, o, _ = self._sum(self.msgs.values())
        return len(self.msgs), i + o

    def fill(self, r: AgentResult) -> bool:
        """Copy final totals into `r`. True when the CLI reported a result of its own."""
        r.input_tokens, r.output_tokens, r.cache_read_tokens = self._sum(self.msgs.values())
        if not self.result:
            return False
        res = self.result  # authoritative totals when the CLI finished by itself
        r.result_subtype = res.get("subtype")
        r.final_text = self.text
        r.cost_usd = float(res.get("total_cost_usd") or 0.0)
        r.turns = int(res.get("num_turns") or r.turns)
        if isinstance(res.get("usage"), dict):
            r.input_tokens, r.output_tokens, r.cache_read_tokens = self._sum([res["usage"]])
        return True


def run_agent(
    cmd: list[str],
    instruction: str,
    cwd,
    env: dict,
    limits: Limits,
    clock=time.monotonic,
    tally=None,
) -> AgentResult:
    """Run the agent, feeding `instruction` on stdin; kill it as soon as a limit is exceeded.
    `tally` is the backend's usage parser (feed/live/fill); defaults to the Claude stream-json one."""
    start = clock()
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", start_new_session=True,
    )  # fmt: skip
    q: queue.Queue = queue.Queue()

    def _feed_stdin():
        try:
            proc.stdin.write(instruction)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    def _reader():
        for line in proc.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=_feed_stdin, daemon=True).start()
    threading.Thread(target=_reader, daemon=True).start()

    tally = tally if tally is not None else _Tally()
    lines, limit, done = [], "none", False
    while not done:
        remaining = limits.wall_s - (clock() - start)
        try:
            line = q.get(timeout=max(0.05, min(1.0, remaining)))
        except queue.Empty:
            line = ""
        if line is None:
            done = True
        elif line:
            lines.append(line)
            tally.feed(line)
        turns, toks = tally.live()
        limit = evaluate_limits(turns, toks, clock() - start, limits)
        if limit != "none":
            _kill(proc)
            break
    code = _wait(proc)
    return _finish(tally, lines, limit, code, clock() - start, limits)


def _kill(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()


def _wait(proc) -> int | None:
    try:
        return proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _kill(proc)
        return proc.wait()


def _finish(tally, lines, limit, code, elapsed, limits: Limits) -> AgentResult:
    r = AgentResult(limit_hit=limit, exit_code=code, duration_s=elapsed, raw_lines=lines)
    r.turns, _ = tally.live()
    if tally.fill(r) and limit == "none":
        limit = evaluate_limits(r.turns, r.total_tokens, elapsed, limits)
        if limit == "none" and r.result_subtype == "error_max_turns":
            limit = "turns"  # the CLI stopped itself at --max-turns
        r.limit_hit = limit
    return r


def scripted_agent_result(note: str = "scripted agent: no changes made") -> AgentResult:
    """Stub agent for --scripted-agent / --dry-run: does nothing, spends nothing."""
    return AgentResult(final_text=note, result_subtype="scripted", exit_code=0)


def claude_version(claude_bin: str = "claude") -> str:
    try:
        r = subprocess.run([claude_bin, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"
