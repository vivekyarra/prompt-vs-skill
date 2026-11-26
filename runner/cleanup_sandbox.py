"""Manual, best-effort cleanup of leftover trial flags in the SANDBOX project.

Usage: python -m runner.cleanup_sandbox [--prefix join_button_] [--apply]
Needs FS_SANDBOX_ADMIN_KEY and FS_SANDBOX_PROJECT_ID. Lists only unless --apply.
Never touches the experiment project (it never reads FS_EXPERIMENT_SERVER_KEY).

UNVERIFIED: uses the Admin API endpoints documented in runner/flags.py (AdminApiCleaner). The
Flagsmith CLI (npm @flagsmith/cli) may offer a delete command, but its exact name and credential
env vars were not verified here; confirm in Phase 0 and record in docs/verified-facts.md.
"""

from __future__ import annotations

import argparse
import os
import sys

from runner.config import FLAG_NAME_PREFIX
from runner.flags import AdminApiCleaner


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default=FLAG_NAME_PREFIX)
    ap.add_argument("--apply", action="store_true", help="actually delete (default: list only)")
    a = ap.parse_args(argv)
    key, pid = os.environ.get("FS_SANDBOX_ADMIN_KEY"), os.environ.get("FS_SANDBOX_PROJECT_ID")
    if not key or not pid:
        print("FS_SANDBOX_ADMIN_KEY and FS_SANDBOX_PROJECT_ID are required", file=sys.stderr)
        return 2
    if not a.prefix.startswith(FLAG_NAME_PREFIX):
        print(f"refusing prefix not starting with {FLAG_NAME_PREFIX!r}", file=sys.stderr)
        return 2
    c = AdminApiCleaner(key, pid)
    path = f"/api/v1/projects/{pid}/features/?search={a.prefix}"
    n = 0
    while path:
        data = c._req("GET", path) or {}
        for f in data.get("results", []):
            if f.get("name", "").startswith(a.prefix):
                n += 1
                if a.apply:
                    print(f["name"], c.delete_flag(f["name"]))
                else:
                    print(f["name"], "(would delete)")
        nxt = data.get("next")
        path = nxt.replace(c.base, "") if nxt else None
    print(f"{n} flag(s) matched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
