# ruff: noqa: ISC004
"""Aggregate data/trials.jsonl into RESULTS.md (stdlib only).

Every number written to RESULTS.md is computed from the trial log or taken from an
optional --flagsmith-json file. Flagsmith's own numbers are never computed or guessed here.

Usage:
    python analysis/analyze.py [--trials data/trials.jsonl] [--out RESULTS.md]
                               [--flagsmith-json flagsmith.json] [--seed 20261129]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

VARIANTS = ("prompt", "skill")
PRIMARY_CHECKS = ("C1", "C2", "C3", "C4", "C5", "C6")
ALL_CHECKS = PRIMARY_CHECKS + ("C7",)
STACKS = ("react", "node", "python")
WIN_THRESHOLD = 0.95
SRM_BAND = (0.45, 0.55)
SRM_P_FLAG = 0.001
RUNNER_ERROR_LIMIT = 0.05
MC_SAMPLES = 100_000


# ---------------------------------------------------------------- loading


def load_trials(path: Path) -> list[dict]:
    """Read JSONL; skip blank lines; deduplicate by trial_id (first record wins)."""
    if not path.exists():
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        tid = rec.get("trial_id")
        if tid in seen:
            continue
        seen.add(tid)
        out.append(rec)
    return out


# ---------------------------------------------------------------- statistics


def srm_chi_square(n_a: int, n_b: int) -> tuple[float, float]:
    """Chi-square goodness of fit against a 50/50 split, df=1. Returns (chi2, p)."""
    total = n_a + n_b
    if total == 0:
        return 0.0, 1.0
    expected = total / 2
    chi2 = (n_a - expected) ** 2 / expected + (n_b - expected) ** 2 / expected
    return chi2, math.erfc(math.sqrt(chi2 / 2))


def srm_status(n_a: int, n_b: int) -> dict:
    total = n_a + n_b
    chi2, p = srm_chi_square(n_a, n_b)
    share = (n_b / total) if total else 0.5
    outside_band = total > 0 and not (SRM_BAND[0] <= share <= SRM_BAND[1])
    return {
        "chi2": chi2,
        "p": p,
        "share_skill": share,
        "outside_band": outside_band,
        "flagged": outside_band or p < SRM_P_FLAG,
    }


def percentile(sorted_vals: list[float], q: float) -> float:
    idx = q * (len(sorted_vals) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def beta_binomial_diff(
    succ_a: int, n_a: int, succ_b: int, n_b: int, seed: int = 1, samples: int = MC_SAMPLES
) -> dict:
    """Beta(1,1) priors. Difference is B - A (B = skill, A = prompt)."""
    rng = random.Random(seed)
    diffs = []
    wins_b = 0
    for _ in range(samples):
        pa = rng.betavariate(1 + succ_a, 1 + n_a - succ_a)
        pb = rng.betavariate(1 + succ_b, 1 + n_b - succ_b)
        diffs.append(pb - pa)
        wins_b += pb > pa
    diffs.sort()
    return {
        "p_b_better": wins_b / samples,
        "ci_low": percentile(diffs, 0.025),
        "ci_high": percentile(diffs, 0.975),
        "mean_diff": sum(diffs) / samples,
    }


def beta_interval(succ: int, n: int, seed: int = 1, samples: int = MC_SAMPLES) -> tuple[float, float]:
    """95% credible interval of one arm's pass rate: same Beta(1,1) posterior and Monte Carlo as above."""
    rng = random.Random(seed)
    draws = sorted(rng.betavariate(1 + succ, 1 + n - succ) for _ in range(samples))
    return percentile(draws, 0.025), percentile(draws, 0.975)


def extra_trials_needed(p_a: float, p_b: float, n_now_per_arm: int) -> int | None:
    """Rough normal approximation: trials per arm for ~80% power at alpha 0.05, assuming the
    observed difference is real. Returns the EXTRA trials per arm, or None if not estimable."""
    delta = abs(p_b - p_a)
    if delta < 1e-9:
        return None
    pbar = (p_a + p_b) / 2
    var = max(pbar * (1 - pbar), 0.01)
    n_needed = 2 * (1.96 + 0.84) ** 2 * var / delta**2
    return max(0, math.ceil(n_needed) - n_now_per_arm)


def decide(primary: dict, guardrail: dict, n_per_arm: tuple[int, int], rates: tuple[float, float]) -> dict:
    """Apply the pre-registered rule exactly (EXPERIMENT.md / BUILD_SPEC section 2).

    primary / guardrail are beta_binomial_diff outputs (difference = skill - prompt).
    Ship the leading variant only if: win prob >= 95% AND the 95% interval on the difference
    excludes zero AND the guardrail (over_budget, lower is better) is not significantly worse
    for it. Otherwise inconclusive.
    """
    if min(n_per_arm) == 0:
        return {"outcome": "no data", "winner": None, "reasons": ["a variant has zero trials"], "extra": None}
    winner = "skill" if primary["p_b_better"] >= 0.5 else "prompt"
    win_prob = primary["p_b_better"] if winner == "skill" else 1 - primary["p_b_better"]
    ci_excludes_zero = primary["ci_low"] > 0 or primary["ci_high"] < 0
    # guardrail diff is skill - prompt; "significantly worse for winner" = winner's over_budget
    # higher with the interval excluding zero.
    worse = guardrail["ci_low"] > 0 if winner == "skill" else guardrail["ci_high"] < 0
    reasons = []
    if win_prob < WIN_THRESHOLD:
        reasons.append(f"win probability {win_prob:.1%} is below {WIN_THRESHOLD:.0%}")
    if not ci_excludes_zero:
        reasons.append("95% credible interval on the difference includes zero")
    if worse:
        reasons.append("guardrail (over_budget) is significantly worse for the leading variant")
    if reasons:
        extra = extra_trials_needed(rates[0], rates[1], min(n_per_arm))
        return {"outcome": "inconclusive", "winner": winner, "reasons": reasons, "extra": extra,
                "win_prob": win_prob}
    return {"outcome": "ship", "winner": winner, "reasons": [], "extra": None, "win_prob": win_prob}


# ---------------------------------------------------------------- aggregation


def _mean(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def summarise(trials: list[dict]) -> dict:
    by_var: dict[str, list[dict]] = {v: [] for v in VARIANTS}
    for t in trials:
        if t.get("variant") in by_var:
            by_var[t["variant"]].append(t)
    out: dict = {"all": {v: len(by_var[v]) for v in VARIANTS}, "variants": {}}
    for v, recs in by_var.items():
        ok = [r for r in recs if not r.get("runner_error")]
        out["variants"][v] = {
            "exposed": len(recs),
            "runner_errors": len(recs) - len(ok),
            "n": len(ok),
            "passed": sum(1 for r in ok if r.get("passed")),
            "over_budget": sum(1 for r in ok if r.get("over_budget")),
            "turns": _mean([r["turns"] for r in ok if r.get("turns") is not None]),
            "tokens": _mean([(r.get("input_tokens") or 0) + (r.get("output_tokens") or 0) for r in ok]),
            "cost": _mean([r["cost_usd"] for r in ok if r.get("cost_usd") is not None]),
            "duration": _mean([r["duration_s"] for r in ok if r.get("duration_s") is not None]),
            "check_fail": {
                c: sum(1 for r in ok if (r.get("checks") or {}).get(c) is False) for c in ALL_CHECKS
            },
            "records": ok,
        }
    return out


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def fmt_num(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def rate(a: int, b: int) -> float | None:
    return a / b if b else None


# ---------------------------------------------------------------- report


CONFIG_KEYS = ("agent", "model", "max_turns", "max_tokens", "repo_sha", "skill_sha", "grader_sha",
               "prompt_sha256", "brief_sha256")  # fmt: skip


def config_lines(trials: list[dict]) -> list[str]:
    """Distinct configuration tuples across the analysed records. More than one tuple means the
    frozen configuration changed mid-run, which must be explained in RESULTS.md."""
    from collections import Counter

    tuples = Counter(tuple(str(t.get(k, "?")) for k in CONFIG_KEYS) for t in trials)
    out = [f"- Configuration tuples seen across {len(trials)} records: **{len(tuples)}** "
           f"({'OK, single frozen configuration' if len(tuples) <= 1 else 'MORE THAN ONE - explain'})."]  # fmt: skip
    for tup, n in tuples.most_common():
        out.append("  - " + ", ".join(f"{k}={v[:12]}" for k, v in zip(CONFIG_KEYS, tup)) + f" (n={n})")
    return out


def render_no_data(generated: str) -> str:
    return (
        "# RESULTS\n\n"
        f"_Generated by `analysis/analyze.py` at {generated}._\n\n"
        "**No data yet.** `data/trials.jsonl` is absent or empty, so no results are reported. "
        "Numbers appear here only once real trials have been collected.\n"
    )


def fs_from_snapshot(snap: dict) -> dict:
    """Turn a raw `ops/snapshot_results.py` snapshot into the fields render_flagsmith shows (no hand-copying).
    Flagsmith calls the control (`prompt`) bucket `control`."""
    pay = snap["results"]["results"]["payload"]
    name = {"control": "prompt", "skill": "skill"}
    metrics = {m["metric_id"]: m for m in pay["metrics"]}
    primary = metrics[min(metrics)]  # integration_verified is listed first / has the lower id
    guard = metrics[max(metrics)]

    def per_arm(m, fmt):
        return {name.get(k, k): fmt(v) for k, v in m["variants"].items()}

    inf = (primary.get("inference") or {}).get("skill") or {}
    out = {
        "exposures": per_arm(primary, lambda v: v["n"]),
        "integration_verified_rate": per_arm(primary, lambda v: f"{v['sum']:.0f}/{v['n']} = {v['sum'] / v['n']:.1%}"),
        "guardrail_over_budget": per_arm(guard, lambda v: f"{v['sum']:.0f}/{v['n']}"),
        "counts": {"exposed": per_arm(primary, lambda v: v["n"]), "converted": per_arm(primary, lambda v: v["sum"])},
        "read_at_utc": snap["results"]["results"].get("as_of") or snap.get("as_of"),
        "screenshot": "TBD - added by a human",
    }
    if inf:
        out["lift"] = f"{inf['lift']:.1%} (skill relative to prompt)"
        out["credible_interval"] = f"[{inf['ci_low']:.3f}, {inf['ci_high']:.3f}] on the absolute difference (skill - prompt)"
        out["win_probability"] = f"skill {inf['chance_to_win']:.6%}; prompt {1 - inf['chance_to_win']:.6%}"
    return out


def render_flagsmith(fs: dict | None) -> list[str]:
    lines = ["## 1. Primary result (from Flagsmith)", ""]
    if not fs:
        return lines + [
            "Flagsmith's dashboard is the source of truth for the primary result. "
            "Not supplied yet (pass `--flagsmith-json`).",
            "",
            "| Field | Value |",
            "|---|---|",
            "| Exposures per variant | TBD - read from Flagsmith dashboard |",
            "| `integration_verified` rate per variant | TBD - read from Flagsmith dashboard |",
            "| Lift | TBD - read from Flagsmith dashboard |",
            "| Credible interval on the difference | TBD - read from Flagsmith dashboard |",
            "| Win probability | TBD - read from Flagsmith dashboard |",
            "| Screenshot | TBD - added by a human |",
            "| Dashboard read at (UTC) | TBD - added by a human |",
            "",
        ]
    lines += ["| Field | Value |", "|---|---|"]
    keys = [
        ("exposures", "Exposures per variant"),
        ("integration_verified_rate", "`integration_verified` rate per variant"),
        ("guardrail_over_budget", "Guardrail `over_budget` events / exposed, per variant"),
        ("lift", "Lift"),
        ("credible_interval", "Credible interval on the difference"),
        ("win_probability", "Win probability"),
        ("screenshot", "Screenshot"),
        ("read_at_utc", "Dashboard read at (UTC)"),
    ]
    for k, label in keys:
        v = fs.get(k)
        shown = json.dumps(v) if isinstance(v, (dict, list)) else (v or "TBD")
        lines.append(f"| {label} | {shown} |")
    lines.append("")
    return lines


def figure_stats(trials: list[dict], seed: int) -> dict | None:
    """Numbers for analysis/figure.py, from the same functions and seeds `render` uses."""
    if not trials:
        return None
    s = summarise(trials)
    p, k = s["variants"]["prompt"], s["variants"]["skill"]
    arms = {"prompt": p, "skill": k}
    rates = {a: rate(d["passed"], d["n"]) for a, d in arms.items()}
    primary = beta_binomial_diff(p["passed"], p["n"], k["passed"], k["n"], seed)
    guard = beta_binomial_diff(p["over_budget"], p["n"], k["over_budget"], k["n"], seed + 1)
    return {
        "n": {a: d["n"] for a, d in arms.items()},
        "passed": {a: d["passed"] for a, d in arms.items()},
        "rate": rates,
        "ci": {a: beta_interval(d["passed"], d["n"], seed) if d["n"] else None for a, d in arms.items()},
        "diff": primary if (p["n"] and k["n"]) else None,
        "decision": decide(primary, guard, (p["n"], k["n"]), (rates["prompt"] or 0.0, rates["skill"] or 0.0)),
        "checks": PRIMARY_CHECKS,
        "check_fail": {a: {c: d["check_fail"][c] for c in PRIMARY_CHECKS} for a, d in arms.items()},
    }


def _fraction(recs: list[dict], key: str) -> str:
    """'x/n (pct)' over records where `key` is a bool; 'unknown' if none carry it."""
    known = [r[key] for r in recs if isinstance(r.get(key), bool)]
    if not known:
        return "unknown"
    return f"{sum(known)}/{len(known)} ({fmt_pct(rate(sum(known), len(known)))})"


def render_fidelity(prompt_recs: list[dict], skill_recs: list[dict]) -> list[str]:
    """Treatment-fidelity block. Descriptive only; never feeds the decision."""
    return [
        "### Treatment fidelity (descriptive; NOT part of the decision)",
        "",
        "Fraction of analysed trials (among records carrying the field) in which the agent loaded the "
        "`flagsmith-ab-test` skill through its skill tool. The prompt arm is expected to be ~0.",
        "",
        "| Variant | `skill_loaded` true |",
        "|---|---|",
        f"| prompt | {_fraction(prompt_recs, 'skill_loaded')} |",
        f"| skill | {_fraction(skill_recs, 'skill_loaded')} |",
        "",
        "**EXPLORATORY:** share of trials where the trial's sandbox flag was created during the trial "
        "(`flag_created_during_trial`; `unknown` where the field is missing or the creation time could "
        "not be determined). Not a pre-registered outcome.",
        "",
        "| Variant | Flag created during trial |",
        "|---|---|",
        f"| prompt | {_fraction(prompt_recs, 'flag_created_during_trial')} |",
        f"| skill | {_fraction(skill_recs, 'flag_created_during_trial')} |",
        "",
    ]


def render(trials: list[dict], fs: dict | None, seed: int, generated: str, figures_rel: str | None = None) -> str:
    if not trials:
        return render_no_data(generated)
    s = summarise(trials)
    p, k = s["variants"]["prompt"], s["variants"]["skill"]
    L: list[str] = [
        "# RESULTS",
        "",
        f"_Generated by `analysis/analyze.py` at {generated} from `data/trials.jsonl` "
        f"({len(trials)} records). Every number below is computed from that log, except the "
        "Flagsmith section, which is supplied separately._",
        "",
    ]
    if figures_rel:
        L += [
            f"![Pass rate per arm, prompt vs skill]({figures_rel}/results.svg)",
            "",
            f"![Failure rate per check, prompt vs skill]({figures_rel}/failures.svg)",
            "",
        ]
    L += render_flagsmith(fs)

    rate_p, rate_k = rate(p["passed"], p["n"]), rate(k["passed"], k["n"])
    ob_p, ob_k = rate(p["over_budget"], p["n"]), rate(k["over_budget"], k["n"])
    primary = beta_binomial_diff(p["passed"], p["n"], k["passed"], k["n"], seed)
    guard = beta_binomial_diff(p["over_budget"], p["n"], k["over_budget"], k["n"], seed + 1)
    decision = decide(primary, guard, (p["n"], k["n"]), (rate_p or 0.0, rate_k or 0.0))

    L += [
        "### Our own-log cross-check (NOT Flagsmith's statistics)",
        "",
        "Computed by us from `data/trials.jsonl` with a Beta(1,1)-prior Beta-Binomial model, "
        f"{MC_SAMPLES:,} Monte Carlo draws, seed {seed}. Runner-error trials are excluded from "
        "the denominators. This is a sanity check on Flagsmith's numbers, not a replacement for them.",
        "",
        "| Variant | Trials analysed | `integration_verified` | Pass rate |",
        "|---|---|---|---|",
        f"| prompt | {p['n']} | {p['passed']} | {fmt_pct(rate_p)} |",
        f"| skill | {k['n']} | {k['passed']} | {fmt_pct(rate_k)} |",
        "",
    ]
    if p["n"] and k["n"]:
        L += [
            f"- P(skill > prompt): {primary['p_b_better']:.1%}",
            f"- 95% credible interval on difference (skill - prompt): "
            f"[{primary['ci_low']:+.3f}, {primary['ci_high']:+.3f}] (mean {primary['mean_diff']:+.3f})",
            "",
        ]
    else:
        L += ["- Not computable: a variant has no analysable trials.", ""]

    L += [
        "## 2. Decision",
        "",
        "Rule, as pre-registered in `EXPERIMENT.md`: ship the winner only if win probability >= 95% "
        "AND the 95% credible interval on the difference excludes zero AND the guardrail is not "
        "significantly worse for it. Otherwise inconclusive. The official decision uses Flagsmith's "
        "numbers; the line below applies the same rule to our own-log cross-check.",
        "",
    ]
    if decision["outcome"] == "ship":
        L.append(f"- **Own-log outcome: SHIP `{decision['winner']}`** (win probability "
                 f"{decision['win_prob']:.1%}).")
    elif decision["outcome"] == "inconclusive":
        L.append("- **Own-log outcome: INCONCLUSIVE.** " + "; ".join(decision["reasons"]) + ".")
        if decision["extra"] is None:
            L.append("- Extra trials needed: not estimable (observed difference is ~0).")
        else:
            L.append(f"- Rough extra trials needed: ~{decision['extra']} per variant, assuming the observed "
                     "difference is real (normal approximation, 80% power, alpha 0.05).")
    else:
        L.append("- No decision possible: a variant has no analysable trials.")
    L.append("")

    L += [
        "## 3. Guardrail and cost",
        "",
        "| Variant | `over_budget` | Rate | Mean turns | Mean tokens | Mean cost (USD) | Mean duration (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, d, r in (("prompt", p, ob_p), ("skill", k, ob_k)):
        L.append(f"| {name} | {d['over_budget']}/{d['n']} | {fmt_pct(r)} | {fmt_num(d['turns'])} | "
                 f"{fmt_num(d['tokens'], 0)} | {fmt_num(d['cost'], 3)} | {fmt_num(d['duration'], 0)} |")
    if p["n"] and k["n"]:
        L += ["", f"Own-log P(skill over_budget rate > prompt) = {guard['p_b_better']:.1%}; 95% interval on "
              f"difference [{guard['ci_low']:+.3f}, {guard['ci_high']:+.3f}]."]
    L.append("")

    srm = srm_status(s["all"]["prompt"], s["all"]["skill"])
    total_all = len(trials)
    err_total = p["runner_errors"] + k["runner_errors"]
    err_rate = err_total / total_all if total_all else 0.0
    srm_verdict = "FLAGGED - pause and investigate before trusting any result" if srm["flagged"] else "OK"
    err_verdict = "OVER the 5% limit - pause and fix" if err_rate > RUNNER_ERROR_LIMIT else "under 5%"
    L += [
        "## 4. Sanity checks",
        "",
        f"- Sample ratio (our log, all exposed trials): prompt {s['all']['prompt']}, skill "
        f"{s['all']['skill']} (skill share {srm['share_skill']:.1%}); chi-square = {srm['chi2']:.3f}, "
        f"p = {srm['p']:.4f}. **{srm_verdict}** "
        f"(band {SRM_BAND[0]:.0%}-{SRM_BAND[1]:.0%}; flagged if outside the band or p < {SRM_P_FLAG}).",
        f"- Runner error rate: {err_total}/{total_all} = {err_rate:.1%} (**{err_verdict}**). "
        f"Per variant: prompt {p['runner_errors']}, skill {k['runner_errors']}.",
        *config_lines(trials),
        "- Our-log vs Flagsmith count cross-check: run `python analysis/crosscheck.py --flagsmith-json ...` "
        "(result: TBD - filled after Flagsmith counts are supplied).",
        "",
        "## 5. Where agents fail",
        "",
        "Trials where each check failed (C1-C6 are primary; any failure fails the trial).",
        "",
        "| Check | prompt failures | prompt rate | skill failures | skill rate |",
        "|---|---|---|---|---|",
    ]
    for c in PRIMARY_CHECKS:
        L.append(f"| {c} | {p['check_fail'][c]} | {fmt_pct(rate(p['check_fail'][c], p['n']))} | "
                 f"{k['check_fail'][c]} | {fmt_pct(rate(k['check_fail'][c], k['n']))} |")
    L += [
        "",
        "Example diffs: TBD - 2-3 anonymised failure diffs selected by a human from the trial "
        "artifacts (`diff.patch`); none are generated automatically.",
        "",
        "## 6. Breakdown by stack (EXPLORATORY - not part of the decision)",
        "",
        "Small per-cell samples; do not draw conclusions.",
        "",
        "| Stack | prompt pass | skill pass |",
        "|---|---|---|",
    ]
    for st in STACKS:
        cells = []
        for d in (p, k):
            recs = [r for r in d["records"] if r.get("stack") == st]
            n_pass = sum(1 for r in recs if r.get("passed"))
            cells.append(f"{n_pass}/{len(recs)} ({fmt_pct(rate(n_pass, len(recs)))})")
        L.append(f"| {st} | {cells[0]} | {cells[1]} |")
    L += [
        "",
        "## 7. C7 diagnostic (server key exposed in client code)",
        "",
        "Diagnostic only; C7 does not affect `integration_verified`.",
        "",
        "| Variant | Trials with C7 failing | Rate |",
        "|---|---|---|",
        f"| prompt | {p['check_fail']['C7']}/{p['n']} | {fmt_pct(rate(p['check_fail']['C7'], p['n']))} |",
        f"| skill | {k['check_fail']['C7']}/{k['n']} | {fmt_pct(rate(k['check_fail']['C7'], k['n']))} |",
        "",
    ]
    L += render_fidelity(p["records"], k["records"])
    L += [
        "## 8. Limitations",
        "",
        "- One agent (Claude Code) and one model; results may differ for other agents and models.",
        "- Small sample apps (React, Node, Python); not real-world codebases.",
        "- The task brief replaces interactive answers a human would give.",
        "- Runner-error trials are excluded from pass-rate denominators (reported separately).",
        "- Our own-log Bayesian numbers are a cross-check with our own priors, not Flagsmith's statistics.",
        "- The stack breakdown is exploratory and underpowered.",
        "",
    ]
    return "\n".join(L)


def load_corrections(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def apply_corrections(trials: list[dict], corrections: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (corrected trials, corrections actually applied). Only confirmed corrections
    (replays_passed == '3/3', new_passed true) are applied; the original verdict is kept in `original_passed`."""
    by_id = {c["trial_id"]: c for c in corrections
             if c.get("new_passed") is True and c.get("replays_passed") == "3/3"}  # fmt: skip
    out, applied = [], []
    for t in trials:
        c = by_id.get(t.get("trial_id"))
        if c and not t.get("passed"):
            t = dict(t, passed=True, original_passed=False, corrected=True)
            t["checks"] = dict(t.get("checks") or {}, **{c["check"]: True})
            applied.append(c)
        out.append(t)
    return out, applied


def corrections_section(raw: list[dict], corrected: list[dict], applied: list[dict]) -> str:
    if not applied:
        return ""

    def counts(ts):
        return {v: (sum(1 for t in ts if t.get("variant") == v and t.get("passed")),
                    sum(1 for t in ts if t.get("variant") == v)) for v in ("prompt", "skill")}  # fmt: skip

    a, b = counts(raw), counts(corrected)
    lines = ["", "## Post-freeze corrections (read before interpreting results)", "",
             "A grader bug found after 40 production trials (the app's existing test ran without the fake "
             "credential variables) wrongly failed C1 for the trials below. The fix is one-directional "
             "(an earlier pass can never become a fail); each trial was replayed 3 times with the final grader "
             "and `integration_verified` was sent afterwards by `ops/backfill_events.py`. Per-arm rates were "
             "already visible when the decision to correct was made. Both views are reported:", "",
             "| view | prompt passed/n | skill passed/n |", "|---|---|---|",
             f"| as originally graded | {a['prompt'][0]}/{a['prompt'][1]} | {a['skill'][0]}/{a['skill'][1]} |",
             f"| as corrected | {b['prompt'][0]}/{b['prompt'][1]} | {b['skill'][0]}/{b['skill'][1]} |", "",
             "Corrected trials: " + ", ".join(f"`{c['trial_id']}` ({c.get('variant', '?')}, {c['check']})" for c in applied)]  # fmt: skip
    return "\n".join(lines) + "\n"


STAGE_CHOICES = ("primary", "replication", "rollout", "all")


def record_stage(rec: dict) -> str:
    """Stage of a record; records without a stage count as primary; rollout assignment is rollout."""
    if rec.get("assignment") == "rollout":
        return "rollout"
    return str(rec.get("stage") or "primary").strip().lower()


def is_experiment_record(rec: dict, stage: str = "primary") -> bool:
    """Only real production trials of the selected stage count. The default (primary) is the
    pre-registered analysis: production, Flagsmith assignment, stage primary (or no stage), not
    dry-run/fake-agent. `replication` is the same rule for stage replication. `rollout` selects
    stage rollout (rollout assignment). `all` takes every stage. Local-assignment, dry-run and
    fake-agent records are never included; `assignment == rollout` is never part of primary or
    replication analysis."""
    if (
        str(rec.get("environment", "")).lower() != "production"
        or rec.get("dry_run")
        or rec.get("fake_agent")
    ):
        return False
    assignment = rec.get("assignment", "flagsmith")
    rstage = record_stage(rec)
    if stage == "rollout":
        return rstage == "rollout"
    if assignment != "flagsmith":
        return stage == "all" and assignment == "rollout"
    return stage == "all" or rstage == stage


def add_stage_header(report: str, stage: str, include_all: bool = False) -> str:
    """State which stage the report analyses, right under the title."""
    if include_all:
        line = "**Stage analysed:** every record in the file (`--include-all`, exploratory only)."
    elif stage == "primary":
        line = "**Stage analysed:** `primary` (the pre-registered experiment; the decision uses this stage alone)."
    elif stage == "all":
        line = "**Stage analysed:** `all` (pooled across stages; secondary, never the decision)."
    else:
        line = f"**Stage analysed:** `{stage}` (not the primary experiment; secondary, never the decision)."
    head, sep, rest = report.partition("\n\n")
    return head + "\n\n" + line + "\n\n" + rest if sep else report + "\n\n" + line + "\n"


def flagged_section(trials: list[dict], flagged: list[dict]) -> str:
    """Sensitivity: results with and without trials whose failure is a documented grader limitation
    (kept as failures in the primary analysis; never part of the decision)."""
    ids = {f["trial_id"] for f in flagged}
    hit = [t for t in trials if t.get("trial_id") in ids]
    if not hit:
        return ""
    rest = [t for t in trials if t.get("trial_id") not in ids]

    def counts(ts):
        return {v: (sum(1 for t in ts if t.get("variant") == v and t.get("passed")),
                    sum(1 for t in ts if t.get("variant") == v)) for v in ("prompt", "skill")}  # fmt: skip

    a, b = counts(trials), counts(rest)
    return "\n".join([
        "", "## Sensitivity: trials failed by a documented grader limitation", "",
        "These trials failed because the agent enabled SDK local evaluation (triggered by the `ser.` prefix of the "
        "grader's fake server key) and the grader's mock does not implement the environment-document endpoint. "
        "They are counted as failures in every primary number (pre-registered rule); this table is a sensitivity "
        "check only and is not part of the decision.", "",
        "| view | prompt passed/n | skill passed/n |", "|---|---|---|",
        f"| primary (flagged trials counted as failures) | {a['prompt'][0]}/{a['prompt'][1]} | {a['skill'][0]}/{a['skill'][1]} |",
        f"| excluding {len(hit)} flagged trial(s) | {b['prompt'][0]}/{b['prompt'][1]} | {b['skill'][0]}/{b['skill'][1]} |", "",
        "Flagged: " + ", ".join(f"`{f['trial_id']}` ({f.get('variant', '?')}, {f.get('stack', '?')})" for f in flagged
                                 if f["trial_id"] in ids),
    ]) + "\n"  # fmt: skip


def crosscheck_section(raw: list[dict], corrected: list[dict], fs: dict | None) -> str:
    """Our log vs Flagsmith's counts, per arm. Exposures count every exposed trial (runner errors included);
    conversions are the passes after the documented corrections."""
    if not fs or "counts" not in fs:
        return ""
    ex = {v: sum(1 for t in raw if t.get("variant") == v) for v in ("prompt", "skill")}
    cv = {v: sum(1 for t in corrected if t.get("variant") == v and t.get("passed")) for v in ("prompt", "skill")}
    rows, ok = [], True
    for v in ("prompt", "skill"):
        fe, fc = fs["counts"]["exposed"].get(v), fs["counts"]["converted"].get(v)
        match = fe == ex[v] and fc == cv[v]
        ok = ok and match
        rows.append(f"| {v} | {ex[v]} | {fe} | {cv[v]} | {None if fc is None else int(fc)} | {'match' if match else 'DIFFERENT'} |")
    return "\n".join(["", "## Cross-check: our log vs Flagsmith's counts", "",
        "| arm | our exposures | Flagsmith exposures | our conversions | Flagsmith conversions | |", "|---|---|---|---|---|---|",
        *rows, "", f"**{'All counts match.' if ok else 'Counts differ: investigate before trusting any result.'}**"]) + "\n"  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", default="data/trials.jsonl")
    ap.add_argument("--out", default="RESULTS.md")
    ap.add_argument("--flagsmith-json", default=None)
    ap.add_argument("--seed", type=int, default=20261129)
    ap.add_argument("--corrections", default="data/corrections.jsonl",
                    help="confirmed post-freeze verdict corrections (applied, and reported with and without)")  # fmt: skip
    ap.add_argument("--flagged", default="data/flagged.jsonl",
                    help="trials failed by a documented grader limitation (sensitivity table only)")  # fmt: skip
    ap.add_argument("--notes", default="data/results_notes.md",
                    help="hand-written explanations appended verbatim to RESULTS.md")  # fmt: skip
    ap.add_argument("--include-all", action="store_true",
                    help="include pilot/local/dry-run records (exploratory only; never for the decision)")  # fmt: skip
    ap.add_argument("--stage", choices=STAGE_CHOICES, default="primary",
                    help="which stage to analyse (default primary = the pre-registered experiment)")  # fmt: skip
    ap.add_argument("--figures-dir", default="assets",
                    help="where results.svg and failures.svg are written (default assets)")  # fmt: skip
    args = ap.parse_args(argv)
    trials = load_trials(Path(args.trials))
    if not args.include_all:
        trials = [t for t in trials if is_experiment_record(t, args.stage)]
    raw_trials = trials
    trials, applied = apply_corrections(trials, load_corrections(Path(args.corrections)))
    fs = json.loads(Path(args.flagsmith_json).read_text()) if args.flagsmith_json else None
    if fs and "results" in fs:  # a raw ops/snapshot_results.py snapshot
        fs = fs_from_snapshot(fs)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        from analysis import figure
    except ImportError:  # run as a script: python analysis/analyze.py
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from analysis import figure

    fig_dir = Path(args.figures_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    stats = figure_stats(trials, args.seed)
    stage_label = "all (include-all)" if args.include_all else args.stage
    (fig_dir / "results.svg").write_text(figure.results_svg(stats, generated, stage_label), encoding="utf-8")
    (fig_dir / "failures.svg").write_text(figure.failures_svg(stats, generated, stage_label), encoding="utf-8")
    rel = Path(os.path.relpath(fig_dir.resolve(), Path(args.out).resolve().parent)).as_posix()
    Path(args.out).write_text(
        add_stage_header(render(trials, fs, args.seed, generated, rel), args.stage, args.include_all)
        + corrections_section(raw_trials, trials, applied)
        + flagged_section(trials, load_corrections(Path(args.flagged)))
        + crosscheck_section(raw_trials, trials, fs)
        + (Path(args.notes).read_text(encoding="utf-8") if args.notes and Path(args.notes).exists() else ""),
        encoding="utf-8",
    )
    print(f"wrote {args.out} ({len(trials)} trials)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
