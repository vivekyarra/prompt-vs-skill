"""Collect trial records from downloaded workflow artifacts into data/trials.jsonl.

Looks for single-object `*.json` files holding a trial record (expected names trial.json /
record.json / trial_record.json; any JSON with trial_id and variant is accepted) or `*.jsonl` files under --artifacts-dir, and appends records whose trial_id is not already present.

Usage: python analysis/collect.py --artifacts-dir artifacts [--out data/trials.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RECORD_NAMES = {"trial.json", "record.json", "trial_record.json"}


def iter_records(root: Path):
    if not root.exists():
        return
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            if p.suffix == ".json":
                # Any single-object JSON with trial_id + variant is a trial record (the runner's
                # exact file name is not assumed; RECORD_NAMES are just the expected ones).
                rec = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(rec, dict) and rec.get("trial_id") and (
                    p.name in RECORD_NAMES or "variant" in rec
                ):
                    yield rec
            elif p.suffix == ".jsonl":
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        rec = json.loads(line)
                        if isinstance(rec, dict) and rec.get("trial_id"):
                            yield rec
        except (json.JSONDecodeError, UnicodeDecodeError):
            print(f"skipping unreadable file: {p}", file=sys.stderr)


def collect(artifacts_dir: Path, out: Path) -> int:
    existing: set[str] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.add(json.loads(line)["trial_id"])
    new = []
    for rec in iter_records(artifacts_dir):
        if rec["trial_id"] in existing:
            continue
        existing.add(rec["trial_id"])
        new.append(rec)
    if new:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            for rec in new:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
    return len(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts-dir", default="artifacts")
    ap.add_argument("--out", default="data/trials.jsonl")
    args = ap.parse_args(argv)
    n = collect(Path(args.artifacts_dir), Path(args.out))
    print(f"appended {n} new record(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
