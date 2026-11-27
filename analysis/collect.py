"""Collect trial records from downloaded workflow artifacts into data/trials.jsonl.

Looks for single-object `*.json` files holding a trial record (expected names trial.json /
record.json / trial_record.json; any JSON with trial_id and variant is accepted) or `*.jsonl` files under --artifacts-dir, and appends records whose trial_id is not already present.

Routing: primary-stage production Flagsmith trials -> --out (data/trials.jsonl); stage replication ->
data/replication.jsonl; stage rollout (or assignment rollout) -> data/rollout.jsonl; everything else
(pilot, local, dry-run, fake-agent) -> data/pilot.jsonl.

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


def is_experiment(rec: dict) -> bool:
    """Real production trials with Flagsmith assignment go to `out`; everything else (pilot, local
    assignment, dry runs, records without an environment) goes to pilot.jsonl beside it."""
    return (
        str(rec.get("environment", "")).lower() == "production"
        and rec.get("assignment", "flagsmith") == "flagsmith"
        and not rec.get("dry_run")
        and not rec.get("fake_agent")
    )


STAGE_FILES = {"replication": "replication.jsonl", "rollout": "rollout.jsonl"}


def route(rec: dict) -> str | None:
    """Destination key for a record: None = main file (primary experiment), 'pilot', 'replication' or
    'rollout'. Non-primary stages are routed by stage whatever the assignment/environment; the pilot
    rules (development, local, dry-run, fake agent) are applied to records of the primary stage."""
    stage = str(rec.get("stage") or "primary").lower()
    if rec.get("assignment") == "rollout":
        stage = "rollout"
    if stage in STAGE_FILES and not rec.get("dry_run") and not rec.get("fake_agent") \
            and rec.get("assignment") != "local":
        return stage
    if stage == "primary" and rec.get("assignment") != "rollout" and is_experiment(rec):
        return None
    return "pilot"


def _ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["trial_id"])
    return ids


def collect(artifacts_dir: Path, out: Path) -> int:
    paths = {None: out, "pilot": out.with_name("pilot.jsonl")}
    paths.update({k: out.with_name(v) for k, v in STAGE_FILES.items()})
    existing: set[str] = set()
    for p in paths.values():
        existing |= _ids(p)
    new: dict = {k: [] for k in paths}
    for rec in iter_records(artifacts_dir):
        if rec["trial_id"] in existing:
            continue
        existing.add(rec["trial_id"])
        new[route(rec)].append(rec)
    for key, recs in new.items():
        path = paths[key]
        if recs:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                for rec in recs:
                    f.write(json.dumps(rec, sort_keys=True) + "\n")
    return sum(len(v) for v in new.values())


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
