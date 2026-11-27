"""Validate an Agent Skill folder: front matter, name match, size, forbidden words."""

import re
import sys
from pathlib import Path

MAX_WORDS = 1500
FORBIDDEN = [
    r"\bgrader\b",
    r"\bhidden\b",
    r"\bC[1-7]\b",
    r"\bthis experiment\b",
    r"\bpre-registered\b",
    r"\btrials?\b",
    r"\bhandoff\b",
]
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_front_matter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        raise ValueError("missing YAML front matter")
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    return fields


def validate(folder: Path) -> list[str]:
    errors = []
    path = folder / "SKILL.md"
    if not path.is_file():
        return ["SKILL.md not found"]
    text = path.read_text(encoding="utf-8")
    try:
        fm = parse_front_matter(text)
    except ValueError as e:
        return [str(e)]
    name, desc = fm.get("name", ""), fm.get("description", "")
    if not name:
        errors.append("front matter missing name")
    elif name != folder.name and folder.name != f"{name}-v2":
        errors.append(f"name {name!r} does not match folder {folder.name!r} (a `-v2` suffix is allowed)")
    elif len(name) > 64 or not NAME_RE.match(name):
        errors.append("invalid name format")
    if not desc or len(desc) > 1024:
        errors.append("description missing or over 1024 chars")
    words = len(text.split())
    if words >= MAX_WORDS:
        errors.append(f"{words} words, limit {MAX_WORDS}")
    for pat in FORBIDDEN:
        if re.search(pat, text, re.IGNORECASE if pat[2:3] != "C" else 0):
            errors.append(f"forbidden pattern: {pat}")
    return errors


if __name__ == "__main__":
    targets = [Path(a) for a in sys.argv[1:]] or [Path("skill/flagsmith-ab-test"), Path("skill/flagsmith-ab-test-v2")]
    failed = False
    for target in targets:
        for e in validate(target):
            print(f"FAIL: {target}: {e}")
            failed = True
    sys.exit(1 if failed else 0)
