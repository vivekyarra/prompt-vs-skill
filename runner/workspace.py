"""Workspace preparation and instruction assembly (spec sections 12 and 13 steps 3-4)."""

from __future__ import annotations

import hashlib
import pathlib
import re
import shutil
import subprocess

from runner.config import (
    CONTROL_VALUE,
    EVENT_NAME,
    FLAG_NAME_PREFIX,
    REPO_ROOT,
    SKILL_NAME,
    SKILL_USER_PROMPT,
    VARIATION_VALUE,
)

PROMPT_START = "<!-- PROMPT_START -->"
PROMPT_END = "<!-- PROMPT_END -->"
SEPARATOR = "\n\n---\n\n"
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")
_EXCLUDES = ("node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", "*.pyc")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def trial_suffix(trial_id: str) -> str:
    """Lowercase [a-z0-9_] form of the trial id, safe inside a flag name."""
    s = re.sub(r"[^a-z0-9]+", "_", trial_id.lower()).strip("_")
    return s or "trial"


def flag_name_for(trial_id: str) -> str:
    return f"{FLAG_NAME_PREFIX}{trial_suffix(trial_id)}"


def extract_prompt(raw: str) -> str:
    """Official prompt body: text between PROMPT_START / PROMPT_END markers in
    prompt/OFFICIAL_PROMPT.md (header metadata stays outside them). Whole file if markers absent."""
    s, e = raw.find(PROMPT_START), raw.find(PROMPT_END)
    if s != -1 and e != -1 and e > s:
        return raw[s + len(PROMPT_START) : e].strip("\n")
    return raw


def load_official_prompt(path: pathlib.Path) -> tuple[str, str]:
    text = extract_prompt(path.read_text(encoding="utf-8"))
    return text, sha256_text(text)


def render_brief(template: str, trial_id: str) -> str:
    values = {
        "TRIAL_SUFFIX": trial_suffix(trial_id),
        "FLAG_NAME": flag_name_for(trial_id),
        "EVENT_NAME": EVENT_NAME,
        "CONTROL_VALUE": CONTROL_VALUE,
        "VARIATION_VALUE": VARIATION_VALUE,
    }
    out = _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)
    left = sorted(set(_PLACEHOLDER.findall(out)))
    if left:
        raise ValueError(f"unresolved placeholders in brief: {left}")
    return out


def load_brief(path: pathlib.Path, trial_id: str) -> tuple[str, str]:
    """Returns (rendered brief, sha256 of the raw template file text)."""
    raw = path.read_text(encoding="utf-8")
    return render_brief(raw, trial_id), sha256_text(raw)


def build_instruction(variant: str, official_prompt: str, brief: str) -> str:
    """Variant A: official prompt + brief. Variant B: one neutral line + the SAME brief."""
    if variant == "prompt":
        head = official_prompt
    elif variant == "skill":
        head = SKILL_USER_PROMPT
    else:
        raise ValueError(f"unknown variant {variant!r}")
    return head + SEPARATOR + brief


def _git(cwd: pathlib.Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout


def prepare_workspace(
    work_dir: pathlib.Path,
    stack: str,
    variant: str,
    apps_dir: pathlib.Path | None = None,
    skill_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Copy baseline app to work_dir/app, install skill (variant 'skill' only), git init + baseline
    commit (the skill is part of the baseline so it never shows up in the agent's diff)."""
    apps_dir = apps_dir or REPO_ROOT / "apps"
    skill_dir = skill_dir or REPO_ROOT / "skill" / SKILL_NAME
    src = apps_dir / stack
    if not src.is_dir():
        raise FileNotFoundError(f"baseline app not found: {src}")
    ws = work_dir / "app"
    shutil.copytree(src, ws, ignore=shutil.ignore_patterns(*_EXCLUDES))
    if variant == "skill":
        if not skill_dir.is_dir():
            raise FileNotFoundError(f"skill dir not found: {skill_dir}")
        shutil.copytree(skill_dir, ws / ".claude" / "skills" / SKILL_NAME)
    _git(ws, "init", "-q")
    _git(ws, "config", "user.name", "trial-runner")
    _git(ws, "config", "user.email", "runner@invalid")
    with open(ws / ".git" / "info" / "exclude", "a", encoding="utf-8") as f:
        f.write("node_modules/\n__pycache__/\n.venv/\n*.pyc\ndist/\n")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "--allow-empty", "-m", "baseline")
    return ws


def capture_diff(ws: pathlib.Path) -> str:
    _git(ws, "add", "-A")
    return _git(ws, "diff", "--cached", "--binary", "HEAD")


def tree_sha(path: pathlib.Path) -> str:
    """Git tree sha of a repo folder if available, else a content hash of the folder."""
    try:
        rel = path.resolve().relative_to(REPO_ROOT)
        r = subprocess.run(
            ["git", "rev-parse", f"HEAD:{rel.as_posix()}"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )  # fmt: skip
        return r.stdout.strip()
    except (subprocess.CalledProcessError, ValueError, OSError):
        h = hashlib.sha256()
        if path.is_dir():
            for p in sorted(path.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts:
                    h.update(p.relative_to(path).as_posix().encode())
                    h.update(p.read_bytes())
        return "content-sha256:" + h.hexdigest()
