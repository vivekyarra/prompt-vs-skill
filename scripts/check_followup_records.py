"""Operational check of skill v2 follow-up trial records. Reads files only: no network, no credentials.

    python scripts/check_followup_records.py data/followup.jsonl [--expect 110] [--cap-usd 20]

Run it after every batch (docs/followup-runbook.md). It checks that every record is a real follow-up trial with the
frozen configuration and skill v2, and prints counts, the sample ratio, runner errors, limit hits and cost.
It prints NO pass rate: the follow-up is not stopped or extended because of how a result looks.
Exit code 1 when a check fails (FAIL lines); WARN lines do not fail.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections import Counter

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from analysis.analyze import RUNNER_ERROR_LIMIT, load_trials, percentile, srm_status  # noqa: E402

TARGET = 110  # EXPERIMENT.md, "Follow-up experiment: skill v2 vs the official prompt"
# Frozen values (EXPERIMENT.md, "Set in pilot" and the freeze log) plus what the follow-up declaration fixes.
EXPECTED = {
    "stage": "followup",
    "skill_dir": "skill/flagsmith-ab-test-v2",
    "environment": "production",
    "assignment": "flagsmith",
    "agent": "opencode",
    "model": "MiniMaxAI/MiniMax-M3.1-Flash",
    "max_turns": 220,
    "max_tokens": 12_000_000,
}
SAME_AS_PRIMARY = ("prompt_sha256", "brief_sha256")  # the official prompt and the brief must be the primary run's
SINGLE_VALUED = ("skill_sha", "grader_sha", "repo_sha", "agent_version")


def check(rows: list[dict], primary: list[dict], other_ids: set[str], expect: int | None, cap_usd: float | None,
          target: int = TARGET) -> tuple[list[str], list[str], list[str]]:  # fmt: skip
    """Return (info lines, warnings, failures)."""
    info, warn, fail = [], [], []
    n = len(rows)
    if not n:
        return info, warn, ["no records"]
    for key, want in EXPECTED.items():
        bad = Counter(str(r.get(key)) for r in rows if r.get(key) != want)
        if bad:
            fail.append(f"{key}: expected {want!r} on every record, also found {dict(bad)}")
    test_doubles = [r["trial_id"] for r in rows if r.get("dry_run") or r.get("scripted_agent")]
    if test_doubles:
        fail.append(f"dry-run or scripted-agent records present: {test_doubles[:5]}")
    for key in SAME_AS_PRIMARY:
        ref = {r.get(key) for r in primary if r.get(key)}
        got = {r.get(key) for r in rows if r.get(key)}
        if ref and not got <= ref:
            fail.append(f"{key}: differs from the primary run's ({sorted(str(x)[:12] for x in got - ref)})")
    for key in SINGLE_VALUED:
        vals = Counter(str(r.get(key)) for r in rows if r.get(key))
        info.append(f"{key}: " + ", ".join(f"{v[:12]} (n={c})" for v, c in vals.most_common()))
        if len(vals) > 1:
            fail.append(f"{key}: more than one value across the follow-up records; explain before going on")
    ids = [r.get("trial_id") for r in rows]
    clash = sorted(set(ids) & other_ids)
    if clash:
        fail.append(f"trial ids already present in the primary or replication log: {clash[:5]}")

    arms = Counter(r.get("variant") for r in rows)
    n_p, n_s = arms.get("prompt", 0), arms.get("skill", 0)
    info.append(f"records: {n} (prompt {n_p}, skill {n_s}, no variant {n - n_p - n_s}); target {target}")
    if n > target:
        fail.append(f"{n} records is more than the declared {target}: no further batch, and explain the surplus")
    if expect is not None and n != expect:
        fail.append(f"expected {expect} records, found {n}")
    srm = srm_status(n_p, n_s)
    line = f"sample ratio: skill share {srm['share_skill']:.1%}, chi-square p = {srm['p']:.4f}"
    if srm["p"] < 0.001:
        fail.append(line + " (p < 0.001: assignment is broken, stop)")
    elif srm["outside_band"]:
        (fail if n >= target else warn).append(line + " (outside 45%-55%; expected in a small batch, a stop at the full count)")
    else:
        info.append(line)

    errs = [r for r in rows if r.get("runner_error")]
    line = f"runner errors: {len(errs)}/{n} = {len(errs) / n:.1%} (prompt {sum(r.get('variant') == 'prompt' for r in errs)}, " \
           f"skill {sum(r.get('variant') == 'skill' for r in errs)}, before assignment {sum(not r.get('variant') for r in errs)})"  # fmt: skip
    (fail if len(errs) / n > RUNNER_ERROR_LIMIT else info).append(line + (": over the 5% limit, stop" if len(errs) / n > RUNNER_ERROR_LIMIT else ""))
    for r in errs[:10]:
        info.append(f"  runner error {r.get('trial_id')}: {str(r.get('runner_error_message'))[:120]}")
    ok = [r for r in rows if not r.get("runner_error")]
    limits = Counter(str(r.get("limit_hit") or "none") for r in ok)
    info.append(f"limit hits (analysed trials): {dict(limits)}")

    skill = [r for r in ok if r.get("variant") == "skill"]
    prompt = [r for r in ok if r.get("variant") == "prompt"]
    loaded = sum(bool(r.get("skill_loaded")) for r in skill)
    info.append(f"skill arm loaded the skill: {loaded}/{len(skill)}; prompt arm: {sum(bool(r.get('skill_loaded')) for r in prompt)}/{len(prompt)}")
    if skill and loaded == 0:
        fail.append("no skill-arm trial loaded the skill: the skill folder is not reaching the agent")
    elif skill and loaded < len(skill):
        warn.append(f"{len(skill) - loaded} skill-arm trial(s) did not load the skill (treatment fidelity; report it)")
    if any(r.get("skill_loaded") for r in prompt):
        fail.append("a prompt-arm trial loaded the skill: the arms are contaminated")
    unsent = [r["trial_id"] for r in ok if r.get("passed") and "integration_verified" not in (r.get("events_sent") or [])]
    if unsent:
        fail.append(f"passing trials without a sent integration_verified event: {unsent[:5]}")

    costs = sorted(float(r.get("cost_usd") or 0.0) for r in rows)
    total, mean = sum(costs), sum(costs) / n
    projected = total + mean * max(0, target - n)
    info.append(f"recorded cost: total ${total:.2f}, mean ${mean:.4f}, p90 ${percentile(costs, 0.9):.4f}, max ${costs[-1]:.4f}; "
                f"projected total at {target} trials ${projected:.2f}")  # fmt: skip
    if cap_usd is not None and projected > cap_usd:
        fail.append(f"projected recorded cost ${projected:.2f} is over the cap ${cap_usd:.2f}: stop and ask the owner")
    return info, warn, fail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("records", help="JSONL of follow-up trial records, e.g. data/followup.jsonl")
    ap.add_argument("--expect", type=int, default=None, help="exact number of records expected at this point")
    ap.add_argument("--cap-usd", type=float, default=None, help="owner's cap on recorded spend for the follow-up")
    ap.add_argument("--primary", default=str(REPO / "data" / "trials.jsonl"))
    ap.add_argument("--replication", default=str(REPO / "data" / "replication.jsonl"))
    args = ap.parse_args(argv)
    rows = load_trials(pathlib.Path(args.records))
    primary = load_trials(pathlib.Path(args.primary))
    other = {r.get("trial_id") for r in primary + load_trials(pathlib.Path(args.replication))}
    info, warn, fail = check(rows, primary, other, args.expect, args.cap_usd)
    for tag, lines in (("    ", info), ("WARN", warn), ("FAIL", fail)):
        for line in lines:
            print(f"{tag} {line}")
    print("FOLLOW-UP RECORDS:", "FAIL" if fail else "OK")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
