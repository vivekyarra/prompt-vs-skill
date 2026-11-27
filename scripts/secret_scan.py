"""Minimal secret scan over tracked files (CI). Exits 1 on a hit."""
import re
import subprocess
import sys

PATTERNS = {
    "anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "github token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "flagsmith server key": re.compile(r"\bser\.[A-Za-z0-9]{20,}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws key": re.compile(r"AKIA[0-9A-Z]{16}"),
}


def main() -> int:
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    bad = 0
    for f in files:
        if f.endswith((".lock", ".png", ".jpg", ".svg")) or "package-lock" in f:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for name, pat in PATTERNS.items():
            if pat.search(text):
                print(f"SECRET? {name} in {f}")
                bad += 1
    print("secret scan:", "FAILED" if bad else "clean")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
