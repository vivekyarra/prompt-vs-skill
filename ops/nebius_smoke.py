"""Tool-calling + usage smoke test for candidate Nebius models (a few tokens each, no secrets printed)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = (os.environ.get("NEBIUS_BASE_URL") or "https://api.tokenfactory.nebius.com/v1/").rstrip("/")
KEY = os.environ.get("NEBIUS_API_KEY", "")
CANDIDATES = [
    "MiniMaxAI/MiniMax-M3.1-Flash",
    "zai-org/GLM-5.3-Flash",
    "deepseek-ai/DeepSeek-V4.1-Flash-1017",
    "openai/gpt-oss-120b",
    "nvidia/nemotron-3-super-120b-a12b",
    "Qwen/Qwen3-30B-A3B-Instruct-2507",
]
TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_shell",
        "description": "Run a shell command and return its output.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    },
}]


def call(model: str) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "List the files in the current directory using the run_shell tool."}],
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": 400,
    }
    req = urllib.request.Request(
        BASE + "/chat/completions", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )  # fmt: skip
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
        msg = (data.get("choices") or [{}])[0].get("message", {})
        calls = msg.get("tool_calls") or []
        return {"model": model, "http": 200, "tool_call": bool(calls), "usage": data.get("usage"),
                "seconds": round(time.time() - t0, 1)}  # fmt: skip
    except urllib.error.HTTPError as e:
        return {"model": model, "http": e.code, "error": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:  # noqa: BLE001
        return {"model": model, "http": -1, "error": type(e).__name__}


def main() -> int:
    if not KEY:
        print("NEBIUS_API_KEY not set")
        return 1
    for m in CANDIDATES:
        print(json.dumps(call(m)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
