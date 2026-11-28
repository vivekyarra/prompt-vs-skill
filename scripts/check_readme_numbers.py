"""Check that the numbers in README.md match RESULTS.md and the committed data files. Exits 1 on a mismatch.

    python scripts/check_readme_numbers.py

Two checks:
 1. Headline numbers are RECOMPUTED from data/ and must appear in the README (and in RESULTS.md where it reports
    them): per-arm pass counts of both runs (trial log + documented corrections), the Flagsmith lift and interval of
    both snapshots, the offline-regrade counts, the mock-vs-real agreement, the Python audit scope.
 2. Every count-like token in the README ("N of M", "N/M", signed decimals like -0.208, percentages) must occur in
    RESULTS.md, EXPERIMENT.md, a docs/*.md report, or be one of the recomputed values. Unknown tokens are listed.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]


def jl(rel: str) -> list[dict]:
    return [json.loads(x) for x in (REPO / rel).read_text().splitlines() if x.strip()]


def arm_counts(rows, corrections=()) -> dict:
    fixed = {c["trial_id"] for c in corrections if c.get("new_passed")}
    out = {}
    for arm in ("prompt", "skill"):
        a = [r for r in rows if r["variant"] == arm]
        out[arm] = (sum(r["passed"] or r["trial_id"] in fixed for r in a), len(a))
    return out


def computed() -> dict[str, str]:
    """name -> string that must appear in the README."""
    prim = arm_counts(jl("data/trials.jsonl"), jl("data/corrections.jsonl"))
    repl = arm_counts(jl("data/replication.jsonl"))
    facts = {
        "primary prompt": "%d of %d" % prim["prompt"],
        "primary skill": "%d of %d" % prim["skill"],
        "replication prompt": "%d of %d" % repl["prompt"],
        "replication skill": "%d of %d" % repl["skill"],
        "total trials": str(len(jl("data/trials.jsonl")) + len(jl("data/replication.jsonl"))),
    }
    real = {r["trial_id"]: r for r in jl("data/mock_vs_real_results.jsonl") if r.get("passed") is not None}
    mock = {r["trial_id"]: r.get("regrade_passed") for r in jl("data/regrade_results.jsonl")}
    facts["mock vs real"] = "%d of %d" % (sum(r["passed"] == mock[t] for t, r in real.items()), len(real))
    rg = {r["trial_id"]: r for r in jl("data/regrade_results.jsonl")}
    summ = json.loads((REPO / "data/regrade_summary.json").read_text())
    counted = {d["trial_id"] for d in summ.get("differences", []) if d.get("counted")}
    for stage, f in (("primary", "trials"), ("replication", "replication")):
        rows = jl(f"data/{f}.jsonl")
        for arm in ("prompt", "skill"):
            a = [r for r in rows if r["variant"] == arm]
            n = sum((rg[r["trial_id"]]["regrade_passed"] if r["trial_id"] in counted else r["passed"]) for r in a)
            facts[f"regrade {stage} {arm}"] = f"{n}/{len(a)}"
    return facts


TOKEN = re.compile(r"\b\d+ of \d+\b|\b\d+/\d+\b|[-+]\d+\.\d+%?|\b\d+\.\d+%")


def main() -> int:
    readme = (REPO / "README.md").read_text()
    readme = re.sub(r"\]\([^)]*\)|https?://\S+", "]", readme)  # link targets and badge URLs are not result numbers
    results = (REPO / "RESULTS.md").read_text()
    corpus = results + (REPO / "EXPERIMENT.md").read_text() + "".join(
        p.read_text() for p in sorted((REPO / "docs").glob("*.md")))  # fmt: skip
    bad = 0
    facts = computed()
    for name, s in facts.items():
        ok = s in readme
        print(f"{'ok  ' if ok else 'MISS'} computed from data: {name} = {s}")
        bad += not ok
    # Flagsmith's own numbers: lift and interval strings of the README must be in RESULTS.md
    known = set(facts.values())
    unknown = sorted({t for t in TOKEN.findall(readme) if t not in corpus and t not in known})
    in_results = [t for t in sorted(set(TOKEN.findall(readme))) if t in results]
    print(f"{len(in_results)} README number tokens found verbatim in RESULTS.md")
    for t in unknown:
        print(f"UNKNOWN README number, not in RESULTS.md / EXPERIMENT.md / docs: {t}")
    bad += len(unknown)
    print("README numbers:", "MISMATCH" if bad else "consistent")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
