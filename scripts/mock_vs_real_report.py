"""Build data/mock_vs_real_results.jsonl and docs/mock-vs-real.md (exploratory).

    python scripts/mock_vs_real_report.py collect LOG [LOG ...]    MVR_RESULT lines of the ops job logs -> jsonl
    python scripts/mock_vs_real_report.py report                    jsonl + selection + emulator regrade -> doc

The emulator baseline is the offline regrade (data/regrade_results.jsonl, same grader tree), so mock and real
differ only in the Flagsmith backend. The recorded verdict (data/trials.jsonl, data/replication.jsonl) is shown too.
"""

from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.mvr_lib import agreement  # noqa: E402

RESULTS = REPO / "data/mock_vs_real_results.jsonl"
DOC = REPO / "docs/mock-vs-real.md"


def _jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def collect(logs: list[str]) -> int:
    rows: dict[str, dict] = {}
    for lp in logs:
        for line in pathlib.Path(lp).read_text(errors="replace").splitlines():
            i = line.find("MVR_RESULT ")
            if i < 0:
                continue
            r = json.loads(line[i + len("MVR_RESULT "):])
            if r.get("passed") is not None or r["trial_id"] not in rows:  # a verdict beats an error
                rows[r["trial_id"]] = r
    RESULTS.write_text("".join(json.dumps(rows[k], sort_keys=True) + "\n" for k in sorted(rows)))
    print(f"{len(rows)} trial(s), {sum(r.get('passed') is not None for r in rows.values())} with a verdict")
    return 0


def pct(a: int, n: int) -> str:
    return f"{a}/{n} ({100 * a / n:.1f}%)" if n else "0/0"


def report() -> int:
    sel = json.loads((REPO / "data/mock_vs_real_selection.json").read_text())
    real = {r["trial_id"]: r for r in _jsonl(RESULTS)}
    mock = {r["trial_id"]: {"passed": r.get("regrade_passed"), "failed_checks": r.get("regrade_failed_checks") or []}
            for r in _jsonl(REPO / "data/regrade_results.jsonl")}  # fmt: skip
    recorded = {r["trial_id"]: r["passed"] for f in ("trials", "replication") for r in _jsonl(REPO / f"data/{f}.jsonl")}
    t = agreement(sel, real, mock)
    n_sel = len(sel["failing"]) + len(sel["passing_sample"])
    L = [
        "# Mock vs real Flagsmith: grader agreement (exploratory)",
        "",
        "Exploratory check, declared in `EXPERIMENT.md` (\"Declaration: mock vs real Flagsmith agreement check\") and "
        "selection committed before any run. It does not change the primary decision, the replication result, any "
        "Flagsmith event of experiments 728 or 1142, or any `data/*.jsonl` trial record.",
        "",
        "## Question",
        "",
        "The grader judges every trial against a local Flagsmith emulator (`grader/mock.py`). Would the verdicts be "
        "the same if the agent's app talked to the real Flagsmith?",
        "",
        "## Method",
        "",
        f"- **Selection** (`data/mock_vs_real_selection.json`, seed {sel['seed']}): all {len(sel['failing'])} trials "
        f"recorded as failed in the primary and replication runs, plus {len(sel['passing_sample'])} passing trials "
        f"drawn from the {sel['passing_pool_size']} passing trials with a non-empty diff: {n_sel} trials.",
        "- **Replay:** as in `docs/regrade.md`: copy `apps/<stack>`, apply the saved diff, write env files for the "
        "names the added code reads. The only difference: key names get the real sandbox keys instead of placeholders.",
        "- **Real backend:** in the sandbox project only, each trial's flag (same name; agent code hard-codes it) with "
        "control `Join` and option `Join free`, and a running 50/50 experiment `MVR <trial id>` on it, so the SDK "
        "experiment methods report `in_experiment` and send `$flag_exposure`. A pass-through HTTPS proxy "
        "(`ops/mvr_mitm_addon.py`) forwards every `*.flagsmith.com` request unchanged and records it with the real "
        "response in the emulator's record format (`scripts/mvr_lib.py`).",
        "- **Judge:** the frozen `grader/checks.py` (tree `814c527`, unchanged), same stacks, browser visitors and "
        "13 s waits. Real Flagsmith buckets identities by hash, so V1 and V2 can get the same value; then fresh "
        "visitors are added until one differs (the remedy `grader/cli.py` uses under local evaluation). Under local "
        "evaluation C6's expected value is what the real service evaluates for that identity.",
        "- **Baseline (local emulator):** the offline emulator regrade of the same diffs with the same grader tree "
        "(`data/regrade_results.jsonl`). Run: `ops/mock_vs_real_regrade.py` through `ops.yml` (environment "
        "development, sandbox keys). Results: `data/mock_vs_real_results.jsonl`.",
        "",
        "## Agreement",
        "",
        "| group | trials | same verdict | same failed checks |",
        "|---|---|---|---|",
    ]
    for k, v in t["by"].items():
        L.append(f"| {k} | {v['n']} | {pct(v['agree'], v['n'])} | {pct(v['checks_agree'], v['n'])} |")
    n = t["by"]["overall"]["n"]
    fail_ids = {x["trial_id"] for x in sel["failing"]}
    real_pass = sorted(k for k in fail_ids if real.get(k, {}).get("passed"))
    emu_pass = [k for k in real_pass if mock[k]["passed"]]
    L += ["", f"Agreement is with the emulator REGRADE, not with the recorded verdict: {len(real_pass)} of the "
          f"{sum(k in real for k in fail_ids)} recorded failures pass on real Flagsmith, and {len(emu_pass)} of those "
          "already pass in the emulator regrade (the 3 C1 corrections and the 8 local-evaluation trials of "
          "`docs/regrade.md`)."]
    L += ["", "Per check (same pass/fail on the local emulator and on real Flagsmith; the declaration named C2-C6, all seven are shown):", "", "| check | agree |", "|---|---|"]
    L += [f"| {c} | {pct(a, n)} |" for c, a in t["per_check"].items()]
    L += ["", "## Disagreements (verdict differs)", ""]
    if not t["disagreements"]:
        L.append("None.")
    for x in t["disagreements"]:
        rr = real[x["trial_id"]]
        L.append(f"- `{x['trial_id']}` ({x['stage']}, {x['variant']}, {x['stack']}): emulator "
                 f"{'pass' if x['mock']['passed'] else 'fail ' + ','.join(x['mock']['failed_checks'])}, real "
                 f"{'pass' if rr['passed'] else 'fail ' + ','.join(rr['failed_checks'])}; recorded "
                 f"{'pass' if recorded.get(x['trial_id']) else 'fail'}.")  # fmt: skip
    L += ["", "## Same verdict, different failed checks", ""]
    if not t["check_differences"]:
        L.append("None.")
    for x in t["check_differences"]:
        L.append(f"- `{x['trial_id']}`: emulator {x['mock']['failed_checks']}, real {x['real']['failed_checks']}")
    L += ["", "## Not compared", ""]
    L += [f"- `{x['trial_id']}`: {x['why']}" + (f" ({real[x['trial_id']].get('error')})" if
          x["trial_id"] in real and real[x["trial_id"]].get("error") else "") for x in t["not_compared"]] or ["None."]  # fmt: skip
    rr = list(real.values())
    statuses = sorted({s for x in rr for s in x.get("http_status") or []})
    L += [
        "",
        "## What the real service did",
        "",
        f"- Every Flagsmith response recorded was a success: {', '.join(f'`{s}`' for s in statuses)} (kind:HTTP "
        f"status). {sum(bool(x.get('http_status')) for x in rr)} of the {len(rr)} replays reached Flagsmith; "
        + ", ".join(f"`{x['trial_id']}`" for x in rr if not x.get("http_status"))
        + " sent no request on either backend (it fails C2-C6 on both).",
        f"- {sum(bool(x.get('local_evaluation')) for x in rr)} replays downloaded the real environment document and "
        "evaluated locally (the skill-arm Node trials flagged in `data/flagged.jsonl`).",
        f"- {sum(bool((x.get('button_text') or {}).get('extra')) for x in rr)} replays needed extra visitors because "
        "real bucketing gave V1 and V2 the same value.",
        "",
        "## Root cause of the C6 differences",
        "",
        "Both C6 differences are prompt-arm React apps (replication) that choose the button text from the variant KEY, "
        "not the value: `flag?.variant === VARIANT_KEY ? VARIANT_LABEL : CONTROL_LABEL` with `VARIANT_KEY = 'join_free'` (the added lines are quoted per trial in `data/variant_key_audit.jsonl`). The emulator (`grader/mock.py`) returns "
        "synthetic keys `variant_0` / `variant_1`, so such an app always shows `Join` and fails C6 whenever the "
        "emulator serves `Join free`. Real Flagsmith returns the option's own key. This is a limitation of the "
        "emulator (a false fail), not of the apps. The real pass depends on the option key in the sandbox being "
        "`join_free`, the key this harness creates; it is also the key both agents created and documented in their "
        "own diffs. In `trial-45967755797-1` the verdict stays fail on both backends because C1 fails (its own test).",
        "",
        "## How many trials does the variant-key gap touch? (exploratory)",
        "",
    ]
    vk = _jsonl(REPO / "data/variant_key_audit.jsonl")
    with_diff = [x for x in vk if x.get("diff_bytes")]
    compare = [x for x in with_diff if x["n_variant_compare"]]
    key_only = [x for x in compare if not x["reads_value"]]
    L += [
        f"`ops/variant_key_audit.py` (ops runs 46126189089, 46126191750) read the artifact of all {len(vk)} trials: "
        f"{len(with_diff)} have a non-empty diff. {len(compare)} add a source line that compares something named "
        f"`variant` (regex, tests and docs excluded; `data/variant_key_audit.jsonl`). In {len(compare) - len(key_only)} "
        "of them the same code also reads the flag value (the comparison is a fallback, a diagnostic, or on the value "
        f"itself). {len(key_only)} choose the text from the variant key alone: "
        + ", ".join(f"`{x['trial_id']}`" for x in key_only)
        + ". Both were already in this sample. So, as far as a regex over added lines can tell, the gap touched no "
        "other trial, and exactly one recorded verdict is an emulator false fail: `trial-45967760241-64` "
        "(replication, prompt arm).",
        "",
        "Sensitivity (exploratory, not a correction; Beta(1,1) Beta-Binomial from `analysis/analyze.py`, seed 20261129, "
        "denominators as in `docs/regrade.md`):",
        "",
        "| view | prompt | skill | difference (skill-prompt), 95% CI |",
        "|---|---|---|---|",
    ]
    from analysis.analyze import beta_binomial_diff

    summ = json.loads((REPO / "data/regrade_summary.json").read_text())["sensitivity"]

    def frac(s):
        a, b = s.split("/")
        return int(a), int(b)

    def row(label, p, s):
        d = beta_binomial_diff(p[0], p[1], s[0], s[1], seed=20261129)
        lo, hi = d["ci_low"], d["ci_high"]
        diff = s[0] / s[1] - p[0] / p[1]
        return f"| {label} | {p[0]}/{p[1]} | {s[0]}/{s[1]} | {diff:+.3f} [{lo:+.3f}, {hi:+.3f}] |"

    pp, ps = frac(summ["primary"]["regraded_counted"]["prompt"]), frac(summ["primary"]["regraded_counted"]["skill"])
    rp, rs = frac(summ["replication"]["regraded_counted"]["prompt"]), frac(summ["replication"]["regraded_counted"]["skill"])
    L += [
        row("replication, regraded (docs/regrade.md)", rp, rs),
        row("replication, regraded + the variant-key false fail counted as a pass", (rp[0] + 1, rp[1]), rs),
        row("both runs pooled, regraded (secondary, descriptive)", (pp[0] + rp[0], pp[1] + rp[1]), (ps[0] + rs[0], ps[1] + rs[1])),
        row("both runs pooled, regraded + the variant-key false fail", (pp[0] + rp[0] + 1, pp[1] + rp[1]), (ps[0] + rs[0], ps[1] + rs[1])),
        "",
        "The fix would favour the prompt arm by one trial and changes no conclusion. The recorded verdicts, the "
        "Flagsmith events and the pre-registered decision are not changed. Both known emulator limitations are now "
        "quantified: local evaluation (8 trials, skill arm, `docs/regrade.md`) and the variant key (1 trial, prompt arm).",
        "",
    ]
    L += [
        "## Runs",
        "",
        "- Reported: ops workflow runs 46121487717, 46121490475, 46121493473, 46121496011 (shards 0-3 of 4, "
        "branch `claude/optimistic-tesla-chhr1a`, environment development, sandbox project only).",
        "- Before: run 46119629420 failed at the first artifact download (auth header sent across the redirect), no "
        "verdict; run 46120467895 graded 4 trials as a smoke test (all pass, the same verdicts and failed checks as "
        "in the reported run). Fix between them: artifact download, Node pinned to 22 (the runner had 24).",
        "- Sandbox objects: one flag and one experiment `MVR <trial id>` per trial in the sandbox Development "
        "environment (`development` is also the GitHub Actions environment name). No object, flag or event of the "
        "experiment project (experiments 728, 1142, 1058, 1414) was read or written.",
    ]
    L += [
        "",
        "## Limits",
        "",
        "- Exploratory, one replay per trial on the real service (the emulator baseline had up to 3).",
        "- The replay is not the original run: the agent's untracked env files are lost (see `docs/regrade.md`).",
        "- Each replay uses a fresh sandbox flag and experiment, not the trial's original sandbox state.",
        "- Real identity bucketing is random per identity; the emulator's is fixed. C6 is compared per identity.",
        "",
    ]
    DOC.write_text("\n".join(L))
    print(f"wrote {DOC.relative_to(REPO)}: overall {pct(t['by']['overall']['agree'], n)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "collect":
        sys.exit(collect(sys.argv[2:]))
    if len(sys.argv) == 2 and sys.argv[1] == "report":
        sys.exit(report())
    sys.exit(__doc__)
