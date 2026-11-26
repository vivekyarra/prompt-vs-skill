"""Credential preflight: checks that the configured secrets work, without printing any secret.

Used by .github/workflows/preflight.yml. Prints only names, ids, counts and model pricing.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

FLAGS_URL = "https://edge.api.flagsmith.com/api/v1/flags/"
ADMIN_URL = "https://api.flagsmith.com/api/v1"
NEBIUS_URL = (os.environ.get("NEBIUS_BASE_URL") or "https://api.tokenfactory.nebius.com/v1/").rstrip("/")


def get(url: str, headers: dict) -> tuple[int, object]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001 - report, never crash the preflight
        return -1, str(type(e).__name__)


def main() -> int:
    ok = True
    lines = []

    def rec(name: str, good: bool, note: str = "") -> None:
        nonlocal ok
        ok = ok and good
        lines.append(f"| {name} | {'OK' if good else 'FAIL'} | {note} |")

    for env_name in ("FS_EXPERIMENT_SERVER_KEY", "FS_SANDBOX_CLIENT_KEY", "FS_SANDBOX_SERVER_KEY"):
        key = os.environ.get(env_name, "")
        if not key:
            rec(env_name, False, "not set")
            continue
        code, _ = get(FLAGS_URL, {"X-Environment-Key": key})
        rec(env_name, code == 200, f"flags endpoint HTTP {code}")

    admin, pid = os.environ.get("FS_SANDBOX_ADMIN_KEY", ""), os.environ.get("FS_SANDBOX_PROJECT_ID", "")
    if not admin or not pid:
        rec("FS_SANDBOX_ADMIN_KEY / PROJECT_ID", False, "not set")
    else:
        h = {"Authorization": f"Api-Key {admin}"}
        code, data = get(f"{ADMIN_URL}/projects/{pid}/", h)
        name = data.get("name") if isinstance(data, dict) else None
        rec("sandbox admin key + project", code == 200, f"HTTP {code}, project name: {name}")
        code, data = get(f"{ADMIN_URL}/environments/?project={pid}", h)
        envs = [e.get("name") for e in (data or {}).get("results", [])] if isinstance(data, dict) else []
        rec("sandbox environments", code == 200 and bool(envs), f"HTTP {code}, environments: {envs}")

    nkey = os.environ.get("NEBIUS_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not nkey:
        rec("Nebius key", False, "not set")
    else:
        code, data = get(f"{NEBIUS_URL}/models?verbose=true", {"Authorization": f"Bearer {nkey}"})
        models = (data or {}).get("data", []) if isinstance(data, dict) else []
        rec("Nebius models list", code == 200 and bool(models), f"HTTP {code}, {len(models)} models")
        if models:
            lines.append("")
            lines.append("<details><summary>Nebius models (id, pricing)</summary>\n")
            for m in models:
                lines.append(f"- `{m.get('id')}` pricing={json.dumps(m.get('pricing'))}")
            lines.append("\n</details>")

    out = "| check | result | note |\n|---|---|---|\n" + "\n".join(lines)
    print(out)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(out + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
