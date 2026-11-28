"""Select the trials for the mock-vs-real Flagsmith agreement check (exploratory).

Selection rule, fixed before any real-Flagsmith regrade is run:
  * every trial whose recorded verdict is a failure (`passed` is false) in data/trials.jsonl (primary)
    and data/replication.jsonl (replication), as logged, before corrections;
  * plus 20 passing trials drawn at random with seed 20261128 from the passing trials of both runs
    that have a non-empty saved diff (an empty or missing diff cannot be replayed, see docs/regrade.md).

The output (data/mock_vs_real_selection.json) is committed before any regrade against real Flagsmith runs.
Reads data/ only; writes one new file; never edits data/*.jsonl.

    python scripts/mock_vs_real_select.py --out data/mock_vs_real_selection.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random

SEED = 20261128
N_PASSING = 20
RUNS = (("primary", "data/trials.jsonl"), ("replication", "data/replication.jsonl"))


def _load(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def select(root: pathlib.Path, seed: int = SEED, n_passing: int = N_PASSING) -> dict:
    diff_bytes = {r["trial_id"]: r.get("diff_bytes") for r in _load(root / "data/regrade_results.jsonl")}
    failing, passing_pool = [], []
    for stage, rel in RUNS:
        for r in _load(root / rel):
            row = {
                "trial_id": r["trial_id"],
                "stage": stage,
                "variant": r["variant"],
                "stack": r["stack"],
                "flag_name": r["flag_name"],
                "recorded_passed": r["passed"],
                "diff_bytes": diff_bytes.get(r["trial_id"]),
            }
            if not r["passed"]:
                failing.append(row)
            elif row["diff_bytes"]:
                passing_pool.append(row)
    passing_pool.sort(key=lambda x: x["trial_id"])
    passing = sorted(random.Random(seed).sample(passing_pool, n_passing), key=lambda x: x["trial_id"])
    return {
        "label": "exploratory",
        "rule": "all recorded failures (primary + replication) + %d random passing trials with a non-empty diff" % n_passing,
        "seed": seed,
        "passing_pool_size": len(passing_pool),
        "failing": sorted(failing, key=lambda x: x["trial_id"]),
        "passing_sample": passing,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default="data/mock_vs_real_selection.json")
    a = ap.parse_args(argv)
    sel = select(pathlib.Path(a.root), seed=a.seed)
    pathlib.Path(a.out).write_text(json.dumps(sel, indent=2) + "\n")
    print(f"failing {len(sel['failing'])}, passing sample {len(sel['passing_sample'])} of {sel['passing_pool_size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
