"""Summarise data/regrade_results.jsonl (offline regrade of the saved diffs) into data/regrade_summary.json.

Applies the counting rule written in docs/regrade.md before any result was read: a trial's ORIGINAL verdict stands
unless ALL hold: the regrade differs, the cause is one of the two named grader changes (C1 test-environment fix, or
the environment-document emulator), and the difference reproduced in 3 of 3 runs. Every other disagreement is listed,
not counted. Uses analysis/analyze.py's Beta-Binomial functions. Reads data only; sends nothing anywhere.

usage: python scripts/regrade_summary.py [--markdown]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "analysis"))
import analyze  # noqa: E402

DATA = REPO / "data"
SEED = 20261129
POOR_AGREEMENT = 0.95  # fixed in docs/regrade.md before any result was read
PRE_FIX_GRADER = "3858b6b"


def jl(path: pathlib.Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def cause_of(row: dict) -> list[str]:
    c = []
    regrade_failed = row.get("regrade_failed_checks")  # None = no regrade result; [] = every check passed
    if (row.get("original_grader_sha") or "").startswith(PRE_FIX_GRADER) and "C1" in row["original_failed_checks"] \
            and regrade_failed is not None and "C1" not in regrade_failed:  # fmt: skip
        c.append("c1_test_env_fix")
    if row.get("local_evaluation"):
        c.append("environment_document")
    return c


def classify(row: dict) -> dict:
    row = dict(row)
    row["causes"] = cause_of(row)
    flipped = bool(row.get("flipped"))
    row["counted"] = bool(flipped and row.get("flip_reproduced") and row["causes"])
    return row


def arm_counts(verdicts: dict[str, bool], variant_of: dict[str, str]) -> dict:
    out = {"prompt": [0, 0], "skill": [0, 0]}
    for tid, ok in verdicts.items():
        a = out[variant_of[tid]]
        a[1] += 1
        a[0] += bool(ok)
    return out


def diff_of(c: dict) -> dict:
    (pp, pn), (sp, sn) = c["prompt"], c["skill"]
    d = analyze.beta_binomial_diff(pp, pn, sp, sn, SEED)
    return {"prompt": f"{pp}/{pn}", "skill": f"{sp}/{sn}", "prompt_rate": round(pp / pn, 4),
            "skill_rate": round(sp / sn, 4), "diff": round(d["mean_diff"], 4),
            "ci": [round(d["ci_low"], 4), round(d["ci_high"], 4)]}  # fmt: skip


def fs_counts(path: pathlib.Path) -> dict:
    snap = json.loads(path.read_text())
    m = snap["results"]["results"]["payload"]["metrics"]
    v = {x["metric_id"]: x for x in m}[min(x["metric_id"] for x in m)]["variants"]
    return {"prompt": [int(v["control"]["sum"]), v["control"]["n"]], "skill": [int(v["skill"]["sum"]), v["skill"]["n"]]}


def build() -> dict:
    rows = [classify(r) for r in jl(DATA / "regrade_results.jsonl")]
    trials = {"primary": jl(DATA / "trials.jsonl"), "replication": jl(DATA / "replication.jsonl")}
    variant_of = {t["trial_id"]: t["variant"] for ts in trials.values() for t in ts}
    flagged = {r["trial_id"] for r in jl(DATA / "flagged.jsonl")}
    corrected = {c["trial_id"] for c in jl(DATA / "corrections.jsonl")
                 if c.get("new_passed") and c.get("replays_passed") == "3/3"}  # fmt: skip
    by_id = {r["trial_id"]: r for r in rows}
    for r in rows:
        r["replayable"] = bool(r.get("diff_bytes"))  # 0-byte diff: the agent committed, nothing to replay
    graded = [r for r in rows if r.get("flipped") is not None]
    no_result = [r for r in rows if r.get("flipped") is None]
    errors = [r["trial_id"] for r in no_result if not (r.get("runner_error") and r.get("diff_bytes") is None)]
    unreplayable = [r["trial_id"] for r in rows if not r["replayable"]]

    nonflag = [r for r in graded if r["trial_id"] not in flagged]
    nonflag_rep = [r for r in nonflag if r["replayable"] and r["trial_id"] not in corrected]
    same = [r for r in nonflag if not r["flipped"]]
    rest = [r for r in nonflag if r["trial_id"] not in corrected]
    rest_same = [r for r in rest if not r["flipped"]]
    agreement = {
        "non_flagged_graded": len(nonflag), "same_verdict": len(same),
        "rate_all_non_flagged": round(len(same) / len(nonflag), 4) if nonflag else None,
        "excluding_documented_c1_corrections": {"n": len(rest), "same": len(rest_same),
                                                "rate": round(len(rest_same) / len(rest), 4) if rest else None},
        "replayable_non_flagged_excluding_documented": {
            "n": len(nonflag_rep), "same": sum(not r["flipped"] for r in nonflag_rep),
            "rate": round(sum(not r["flipped"] for r in nonflag_rep) / len(nonflag_rep), 4) if nonflag_rep else None},
        "poor_threshold": POOR_AGREEMENT,
        "poor": bool(rest) and len(rest_same) / len(rest) < POOR_AGREEMENT,
    }  # fmt: skip
    differences = [
        {k: r.get(k) for k in ("trial_id", "variant", "stack", "original_passed", "original_failed_checks",
                               "regrade_passed", "regrade_failed_checks", "regrade_runs", "causes", "flip_reproduced",
                               "counted", "failure_reasons", "env_placeholders_supplied", "regrade_error")}
        | {"flagged_local_eval": r["trial_id"] in flagged, "documented_c1_correction": r["trial_id"] in corrected}
        for r in graded if r["flipped"]
    ]  # fmt: skip
    checks_changed = [
        {"trial_id": r["trial_id"], "original_failed_checks": r["original_failed_checks"],
         "regrade_failed_checks": r["regrade_failed_checks"]}
        for r in graded if not r["flipped"] and r["checks_changed"]
    ]  # fmt: skip

    per_stage = {}
    for stage, ts in trials.items():
        ids = [t["trial_id"] for t in ts]
        orig = {t["trial_id"]: bool(t["passed"]) for t in ts}
        raw = {i: (by_id[i]["regrade_passed"] if i in by_id and by_id[i].get("flipped") is not None
                   and by_id[i]["replayable"] else orig[i]) for i in ids}  # fmt: skip
        counted = {i: (raw[i] if by_id.get(i, {}).get("counted") else orig[i]) for i in ids}
        fixed = {i: (True if i in corrected else orig[i]) for i in ids}  # as Flagsmith received it (backfilled)
        fsfile = DATA / ("flagsmith_primary_results.json" if stage == "primary" else "flagsmith_replication_results.json")
        per_stage[stage] = {
            "n_trials": len(ids),
            "flagsmith_as_sent": diff_of(fs_counts(fsfile)),
            "as_graded_log": diff_of(arm_counts(orig, variant_of)),
            "as_graded_plus_3_documented_corrections": diff_of(arm_counts(fixed, variant_of)),
            "regraded_counted": diff_of(arm_counts(counted, variant_of)),
            "regraded_raw": diff_of(arm_counts(raw, variant_of)),
            "note": "denominator = every trial record of the arm (runner errors count as not verified), as in Flagsmith",
        }

    versions = sorted({r.get("regrade_grader_version") for r in graded if r.get("regrade_grader_version")})
    problems = []
    if len(rows) != 440:
        problems.append(f"{len(rows)} records, expected 440")
    if errors:
        problems.append(f"{len(errors)} trial(s) without a regrade result: {errors}")
    if len(graded) + len(no_result) != len(rows):
        problems.append("inconsistent row classification")
    if len(versions) != 1:
        problems.append(f"regrade grader versions: {versions}")
    prim = per_stage["primary"]
    if (prim["as_graded_plus_3_documented_corrections"]["prompt"], prim["as_graded_plus_3_documented_corrections"]["skill"]) \
            != (prim["flagsmith_as_sent"]["prompt"], prim["flagsmith_as_sent"]["skill"]):  # fmt: skip
        problems.append("primary as-graded + documented corrections does not equal Flagsmith as sent")
    first40 = [r for r in rows if (r.get("original_grader_sha") or "").startswith(PRE_FIX_GRADER)]
    first40 = sorted(first40, key=lambda r: int(r["trial_id"].split("-")[2]) + 1000 * int(r["trial_id"].split("-")[1]))
    first40_out = [
        {"trial_id": r["trial_id"], "variant": r["variant"], "stack": r["stack"],
         "original": "pass" if r["original_passed"] else "fail:" + ",".join(r["original_failed_checks"]),
         "final_grader": ("pass" if r.get("regrade_passed") else "fail:" + ",".join(r.get("regrade_failed_checks") or []))
         if r.get("flipped") is not None else "error",
         "changed": r.get("flipped"), "flip_reproduced": r.get("flip_reproduced"), "counted": r["counted"]}
        for r in first40
    ]  # fmt: skip
    local = [
        {"trial_id": r["trial_id"], "original_passed": r["original_passed"], "regrade_passed": r.get("regrade_passed"),
         "regrade_failed_checks": r.get("regrade_failed_checks"), "regrade_runs": r.get("regrade_runs"),
         "local_evaluation_seen": r.get("local_evaluation"), "counted": r["counted"],
         "failure_reasons": r.get("failure_reasons")}
        for r in rows if r["trial_id"] in flagged
    ]  # fmt: skip
    flips = [d for d in differences]
    return {
        "records": len(rows), "graded": len(graded), "regrade_errors": errors, "not_replayable_empty_or_missing_diff": unreplayable,
        "completeness_problems": problems,
        "grader_version_regrade": versions,
        "agreement": agreement,
        "flips": {
            "total": len(flips),
            "counted": sum(1 for d in flips if d["counted"]),
            "fail_to_pass": sum(1 for d in flips if d["regrade_passed"] and not d["original_passed"]),
            "pass_to_fail": sum(1 for d in flips if d["original_passed"] and not d["regrade_passed"]),
            "counted_fail_to_pass": sum(1 for d in flips if d["counted"] and d["regrade_passed"]),
            "counted_pass_to_fail": sum(1 for d in flips if d["counted"] and not d["regrade_passed"]),
        },
        "differences": differences,
        "same_verdict_but_failed_checks_changed": checks_changed,
        "flagged_local_evaluation_trials": local,
        "first_40_primary_pre_fix_grader": {"n": len(first40_out), "grader_tree": PRE_FIX_GRADER,
                                            "changed": sum(1 for x in first40_out if x["changed"]),
                                            "trials": first40_out},  # fmt: skip
        "sensitivity": per_stage,
    }


def markdown(s: dict) -> str:
    out = ["| stage | source | prompt | skill | rates | difference (skill-prompt), 95% CI |", "|---|---|---|---|---|---|"]
    for stage, d in s["sensitivity"].items():
        for key, label in (("flagsmith_as_sent", "Flagsmith as sent"), ("as_graded_log", "as graded (log)"),
                           ("regraded_counted", "regraded, counted rule"), ("regraded_raw", "regraded, raw")):  # fmt: skip
            v = d[key]
            out.append(f"| {stage} | {label} | {v['prompt']} | {v['skill']} | {v['prompt_rate']:.1%} / "
                       f"{v['skill_rate']:.1%} | {v['diff']:+.3f} [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}] |")  # fmt: skip
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--allow-incomplete", action="store_true", help="print the problems instead of failing")
    a = ap.parse_args()
    s = build()
    if s["completeness_problems"]:
        print("INCOMPLETE REGRADE:", *s["completeness_problems"], sep="\n  ")
        if not a.allow_incomplete:
            return 1
    (DATA / "regrade_summary.json").write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: s[k] for k in ("records", "graded", "regrade_errors", "agreement", "flips")}, indent=1))
    if a.markdown:
        print(markdown(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
