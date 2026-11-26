#!/usr/bin/env python3
"""Demo: run the grader on a correct reference app and on a broken one (B3) and print a check table.

Prerequisites (one time):
    python -m venv .venv && . .venv/bin/activate
    pip install playwright mitmproxy
    python -m playwright install chromium     # or: export GRADER_CHROME_PATH=/usr/bin/google-chrome
    Node >= 22.21 and npm on PATH.
The first run needs network for `npm ci` (the grader caches installs by lockfile hash, so later runs
need none). Mock mode is used: no proxy, no Flagsmith account, no credentials.

Usage (from the repo root):
    python scripts/demo_grader.py [--stack node|python|react] [--broken B3]
Exit code: 0 when the reference passes and the broken copy fails, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
FLAG = "onboarding_demo"
CHECKS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
NAMES = {
    "C1": "App runs",
    "C2": "Exposure sent",
    "C3": "Conversion on action",
    "C4": "Identity match",
    "C5": "Identity stable",
    "C6": "Flag drives the UI",
    "C7": "No server key in client (diagnostic)",
}


def grade(app_dir: pathlib.Path, stack: str, out: pathlib.Path) -> dict:
    cmd = [
        sys.executable, "-m", "grader", "--app-dir", str(app_dir), "--stack", stack, "--flag", FLAG,
        "--event", "join_clicked", "--variant-values", "Join,Join free", "--out", str(out), "--mode", "mock",
    ]  # fmt: skip
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if not out.exists():
        sys.exit(f"grader error (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return json.loads(out.read_text())


def table(title: str, res: dict) -> None:
    print(f"\n=== {title}: {'PASS' if res['passed'] else 'FAIL'} ===")
    for cid in CHECKS:
        c = res["checks"][cid]
        ok = c.get("passed")
        text = c.get("detail") if ok else c.get("reason")
        text = " ".join(str(text or "").split())
        if len(text) > 70:
            text = text[:67] + "..."
        print(f"  {cid} {NAMES[cid]:<38} {'pass' if ok else 'FAIL':<5} {text}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stack", default="node", choices=("react", "node", "python"))
    ap.add_argument("--broken", default="B3", help="broken variant id from apps/broken (default: B3)")
    a = ap.parse_args()

    subprocess.run(
        [sys.executable, str(ROOT / "apps/broken/make_broken.py"), "--stack", a.stack, "--id", a.broken],
        check=True, cwd=ROOT, stdout=subprocess.DEVNULL,
    )  # fmt: skip
    ref = ROOT / "apps/reference" / a.stack
    broken = ROOT / "apps/broken/_generated" / a.stack / a.broken
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        print(f"Grading the correct reference app ({a.stack}) in mock mode ...", flush=True)
        r1 = grade(ref, a.stack, t / "ref.json")
        print(f"Grading the broken app ({a.stack}/{a.broken}) in mock mode ...", flush=True)
        r2 = grade(broken, a.stack, t / "broken.json")
    table(f"reference {a.stack}", r1)
    table(f"broken {a.stack}/{a.broken}", r2)
    print("\nVerdict = C1..C6 all pass (C7 is diagnostic only).")
    return 0 if (r1["passed"] and not r2["passed"]) else 1


if __name__ == "__main__":
    sys.exit(main())
