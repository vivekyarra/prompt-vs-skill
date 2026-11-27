"""Mechanical flag rule: which FAILED trials enabled SDK local evaluation?

For EVERY failed trial in both arms (trial_record.json `passed: false` and `runner_error: false`) the
agent's diff.patch is checked, on its added lines only, against fixed patterns. The rule is the same for
both arms and involves no judgement:

  * `enableLocalEvaluation\\s*[:=]\\s*` followed by anything but `false` (JS/TS option),
  * `enable_local_evaluation\\s*=\\s*` followed by anything but `False` (Python; includes `= True`),
  * a `startsWith('ser.')` / `.startswith("ser.")` gate, counted only when the same diff also mentions
    local evaluation (such a gate only matters when it feeds the option).

Matches are merged into data/flagged.jsonl ({"trial_id","variant","stack","reason"}), de-duplicated by
trial_id, together with the two entries that were already flagged by hand. REST only, via the `gh` CLI.

usage:
    python scripts/flag_local_eval.py --runs 45914099371 45925699686
    python scripts/flag_local_eval.py --all-production
    python scripts/flag_local_eval.py --artifacts-dir DIR      (already downloaded, one folder per trial)
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = "vivekyarra/prompt-vs-skill"
WORKFLOW = "trials.yml"
REASON_TAIL = "emulator lacks environment-document; not corrected"

# Entries flagged by hand before this script existed (kept verbatim; never duplicated).
HAND_FLAGGED = [
    {"trial_id": "trial-45914099371-12", "variant": "skill", "stack": "node",
     "reason": "grader limitation: agent enabled local evaluation (placeholder 'ser.' key); " + REASON_TAIL},
    {"trial_id": "trial-45925699686-4", "variant": "skill", "stack": "node",
     "reason": "grader limitation: agent enabled local evaluation (placeholder 'ser.' key); " + REASON_TAIL},
]  # fmt: skip

# (id, regex). The `\s` in the lookahead stops `\s*` from backtracking, so that
# `enableLocalEvaluation: false` is not matched.
PATTERNS = [
    ("enableLocalEvaluation", re.compile(r"enableLocalEvaluation\s*[:=]\s*(?!\s|false\b)")),
    ("enable_local_evaluation", re.compile(r"enable_local_evaluation\s*=\s*(?!\s|False\b)")),
]
GATE = re.compile(r"""(?:startsWith|startswith)\(\s*['"]ser\.['"]\s*\)""")
LOCAL_MENTION = re.compile(r"local[_ ]?evaluation", re.IGNORECASE)


def added_lines(diff: str) -> list[str]:
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def scan_diff(diff: str) -> list[str]:
    """Matched pattern ids with the matching snippet; an empty list means the diff does not enable it."""
    lines = added_lines(diff)
    hits: list[str] = []
    for line in lines:
        for pid, rx in PATTERNS:
            if rx.search(line):
                hits.append(f"{pid}: {line.strip()[:80]}")
    joined = "\n".join(lines)
    if GATE.search(joined) and LOCAL_MENTION.search(joined):
        gate = next(ln for ln in lines if GATE.search(ln))
        hits.append(f"ser.-gate: {gate.strip()[:80]}")
    return hits


def is_failed_trial(rec: dict) -> bool:
    return rec.get("passed") is False and rec.get("runner_error") is False


def flag_entry(rec: dict, hits: list[str]) -> dict:
    return {
        "trial_id": rec["trial_id"], "variant": rec.get("variant"), "stack": rec.get("stack"),
        "reason": f"mechanical rule: diff enables SDK local evaluation ({'; '.join(hits[:2])}); " + REASON_TAIL,
    }  # fmt: skip


def merge_flagged(path: Path, new: list[dict]) -> list[dict]:
    """Merge HAND_FLAGGED + existing file + new, de-duplicated by trial_id (earlier wins); write and return."""
    merged: dict[str, dict] = {}
    existing = []
    if path.exists():
        existing = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for e in [*HAND_FLAGGED, *existing, *new]:
        merged.setdefault(e["trial_id"], e)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in merged.values()), encoding="utf-8")
    return list(merged.values())


def count_table(rows: list[dict]) -> str:
    """rows: {"variant", "flagged"} per scanned failed trial -> per-arm count table."""
    out = ["| arm | failed trials scanned | enabled local evaluation |", "|---|---|---|"]
    for arm in ("prompt", "skill"):
        sel = [r for r in rows if r["variant"] == arm]
        out.append(f"| {arm} | {len(sel)} | {sum(1 for r in sel if r['flagged'])} |")
    return "\n".join(out)


def read_trial_dir(files: dict[str, bytes]) -> tuple[dict | None, str]:
    """From {name: bytes} of one artifact -> (trial_record or None, diff text)."""
    rec = diff = None
    for name, data in files.items():
        base = name.rsplit("/", 1)[-1]
        if base == "trial_record.json":
            rec = json.loads(data.decode("utf-8", errors="replace"))
        elif base == "diff.patch":
            diff = data.decode("utf-8", errors="replace")
    return rec, diff or ""


# ---------------------------------------------------------------- gh (REST only)


def gh_bytes(path: str) -> bytes:
    return subprocess.run(["gh", "api", path], capture_output=True, check=True).stdout


def gh_json(path: str):
    return json.loads(gh_bytes(path).decode("utf-8", errors="replace"))


def list_run_ids() -> list[str]:
    ids, page = [], 1
    while True:
        d = gh_json(f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=100&page={page}&status=completed")
        runs = d.get("workflow_runs", [])
        ids += [str(r["id"]) for r in runs]
        if len(runs) < 100:
            return ids
        page += 1


def run_artifacts(run_id: str) -> list[dict]:
    out, page = [], 1
    while True:
        d = gh_json(f"repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100&page={page}")
        arts = d.get("artifacts", [])
        out += [a for a in arts if not a.get("expired")]
        if len(arts) < 100:
            return out
        page += 1


def download_artifact(art: dict) -> dict[str, bytes]:
    z = zipfile.ZipFile(io.BytesIO(gh_bytes(f"repos/{REPO}/actions/artifacts/{art['id']}/zip")))
    return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def iter_remote(run_ids: list[str]):
    for rid in run_ids:
        for art in run_artifacts(rid):
            if art["name"].startswith("trial-"):
                yield art["name"], download_artifact(art)


def iter_local(root: Path):
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        yield d.name, {str(f.relative_to(d)): f.read_bytes() for f in d.rglob("*") if f.is_file()}


def scan(source, production_only: bool) -> tuple[list[dict], list[dict]]:
    flagged, rows = [], []
    for name, files in source:
        rec, diff = read_trial_dir(files)
        if rec is None:
            print(f"skip {name}: no trial_record.json", file=sys.stderr)
            continue
        if production_only and str(rec.get("environment", "")).lower() != "production":
            continue
        if not is_failed_trial(rec):
            continue
        hits = scan_diff(diff)
        rows.append({"variant": rec.get("variant"), "flagged": bool(hits)})
        if hits:
            flagged.append(flag_entry(rec, hits))
    return flagged, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", help="trials.yml run ids")
    ap.add_argument("--all-production", action="store_true",
                    help="every completed trials.yml run, keeping trials whose record says production")  # fmt: skip
    ap.add_argument("--artifacts-dir", type=Path, help="already-downloaded artifacts (one folder per trial)")
    ap.add_argument("--out", type=Path, default=Path("data/flagged.jsonl"))
    a = ap.parse_args(argv)
    if a.artifacts_dir:
        source, prod_only = iter_local(a.artifacts_dir), False
    elif a.runs or a.all_production:
        source, prod_only = iter_remote(a.runs or list_run_ids()), a.all_production
    else:
        ap.error("give --runs, --all-production or --artifacts-dir")
    flagged, rows = scan(source, prod_only)
    merged = merge_flagged(a.out, flagged)
    print(count_table(rows))
    print(f"\n{len(flagged)} match(es) this scan; {len(merged)} entries in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
