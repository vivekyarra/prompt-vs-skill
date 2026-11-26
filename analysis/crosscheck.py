"""Compare our trial-log counts with Flagsmith exposure/event counts.

Flagsmith counts are read from a JSON file only:
    {"exposures": {"prompt": 25, "skill": 24},
     "events": {"integration_verified": {"prompt": 10, "skill": 14}, "over_budget": {...}}}

UNVERIFIED: fetching these from a Flagsmith API is intentionally NOT implemented. No endpoint has
been verified against docs (BUILD_SPEC rule 1), so `fetch_from_api` raises. Use a file exported by
a human from the dashboard.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from analysis.analyze import VARIANTS, load_trials
except ImportError:  # run as a script: python analysis/crosscheck.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from analysis.analyze import VARIANTS, load_trials


def fetch_from_api(*_a, **_k):
    raise NotImplementedError("UNVERIFIED: no Flagsmith results endpoint verified; use --flagsmith-json")


def our_counts(trials: list[dict]) -> dict:
    exposures = {v: 0 for v in VARIANTS}
    events: dict[str, dict[str, int]] = {
        "integration_verified": {v: 0 for v in VARIANTS},
        "over_budget": {v: 0 for v in VARIANTS},
    }
    for t in trials:
        v = t.get("variant")
        if v not in exposures:
            continue
        exposures[v] += 1
        for e in t.get("events_sent") or []:
            if e in events:
                events[e][v] += 1
    return {"exposures": exposures, "events": events}


def compare(ours: dict, theirs: dict, tolerance: float = 0.02) -> list[dict]:
    """Rows of metric/variant/ours/flagsmith/diff/ok. Tolerance is relative, minimum 1 absolute."""
    rows = []

    def add(metric: str, variant: str, a: int, b: int | None):
        if b is None:
            rows.append({"metric": metric, "variant": variant, "ours": a, "flagsmith": None,
                         "diff": None, "ok": False})
            return
        allowed = max(1, tolerance * max(a, b))
        rows.append({"metric": metric, "variant": variant, "ours": a, "flagsmith": b,
                     "diff": b - a, "ok": abs(b - a) <= allowed})

    for v in VARIANTS:
        add("exposures", v, ours["exposures"][v], (theirs.get("exposures") or {}).get(v))
    for ev, per in ours["events"].items():
        for v in VARIANTS:
            add(ev, v, per[v], ((theirs.get("events") or {}).get(ev) or {}).get(v))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", default="data/trials.jsonl")
    ap.add_argument("--flagsmith-json", required=True)
    ap.add_argument("--tolerance", type=float, default=0.02)
    args = ap.parse_args(argv)
    ours = our_counts(load_trials(Path(args.trials)))
    theirs = json.loads(Path(args.flagsmith_json).read_text())
    rows = compare(ours, theirs, args.tolerance)
    for r in rows:
        tag = "MATCH" if r["ok"] else "DIFF"
        print(f"{tag:5} {r['metric']:22} {r['variant']:7} "
              f"ours={r['ours']} flagsmith={r['flagsmith']} diff={r['diff']}")
    ok = all(r["ok"] for r in rows)
    print("RESULT:", "all within tolerance" if ok else "differences found (explain, e.g. events still flushing)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
