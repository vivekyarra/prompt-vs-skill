"""Secret scan over the FULL git history (every commit reachable from any ref), with the patterns of secret_scan.py.

    python scripts/secret_scan_history.py        needs a full clone (not shallow). Exits 1 on a hit.

Scans the added lines of `git log --all -p`. Prints the pattern name, commit and file, never the matching text.
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from secret_scan import PATTERNS  # noqa: E402


def main() -> int:
    if subprocess.check_output(["git", "rev-parse", "--is-shallow-repository"], text=True).strip() == "true":
        print("shallow clone: fetch the full history first (git fetch --unshallow)")
        return 2
    proc = subprocess.Popen(["git", "log", "--all", "-p", "--no-color", "--format=commit %H"], stdout=subprocess.PIPE,
                            text=True, errors="replace")  # fmt: skip
    commit = path = "?"
    commits, hits = 0, set()
    for line in proc.stdout:
        if line.startswith("commit "):
            commit, commits = line.split()[1][:12], commits + 1
        elif line.startswith("+++ "):
            path = line[4:].strip()
        elif line.startswith("+"):
            for name, pat in PATTERNS.items():
                if pat.search(line):
                    hits.add((name, commit, path))
    for name, commit, path in sorted(hits):
        print(f"SECRET? {name} in {path} at {commit}")
    print(f"history secret scan over {commits} commits:", "FAILED" if hits else "clean")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
