"""Record-only: count skill-tool invocations in an agent's JSONL stream.

OpenCode (docs/flagsmith-sdk-notes.md section 9): `{"type":"tool_use","part":{"tool":"skill",
"callID":..., "state":{"input":{"name":"<skill>"}}}}`. Claude Code stream-json carries the same fact as an
assistant content block `{"type":"tool_use","name":"Skill","input":{"skill":"<skill>"}}`. Both are handled so the
count works for either backend. Nothing here influences a trial outcome.
"""

from __future__ import annotations

import json


def _calls(ev: dict):
    """Yield (dedupe_id, skill_name) for each skill-tool call carried by one event."""
    part = ev.get("part")
    if ev.get("type") == "tool_use" and isinstance(part, dict) and str(part.get("tool") or "").lower() == "skill":
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        inp = state.get("input") if isinstance(state.get("input"), dict) else {}
        yield part.get("callID") or part.get("id"), inp.get("name") or inp.get("skill")
    msg = ev.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if ev.get("type") == "assistant" and isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use" and str(b.get("name") or "").lower() == "skill":
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                yield b.get("id"), inp.get("skill") or inp.get("name")


def count_skill_calls(lines, skill_name: str) -> tuple[int, bool]:
    """Return (skill_tool_calls, skill_loaded). Calls with the same id are counted once (a tool part can be
    re-emitted as its state changes). `skill_loaded` is true iff a call named `skill_name`."""
    seen: set[str] = set()
    n, loaded = 0, False
    for line in lines:
        try:
            ev = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(ev, dict):
            continue
        for cid, name in _calls(ev):
            if cid:
                if cid in seen:
                    continue
                seen.add(cid)
            n += 1
            if isinstance(name, str) and name.strip() == skill_name:
                loaded = True
    return n, loaded
