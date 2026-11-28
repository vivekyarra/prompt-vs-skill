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
        "- **Baseline (mock):** the offline emulator regrade of the same diffs with the same grader tree "
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
    L += ["", "Per check (same pass/fail on mock and real):", "", "| check | agree |", "|---|---|"]
    L += [f"| {c} | {pct(a, n)} |" for c, a in t["per_check"].items()]
    L += ["", "## Disagreements (verdict differs)", ""]
    if not t["disagreements"]:
        L.append("None.")
    for x in t["disagreements"]:
        rr = real[x["trial_id"]]
        L.append(f"- `{x['trial_id']}` ({x['stage']}, {x['variant']}, {x['stack']}): mock "
                 f"{'pass' if x['mock']['passed'] else 'fail ' + ','.join(x['mock']['failed_checks'])}, real "
                 f"{'pass' if rr['passed'] else 'fail ' + ','.join(rr['failed_checks'])}; recorded "
                 f"{'pass' if recorded.get(x['trial_id']) else 'fail'}. Real reasons: "
                 f"{json.dumps(rr.get('reasons') or {})[:400]}")  # fmt: skip
    L += ["", "## Same verdict, different failed checks", ""]
    if not t["check_differences"]:
        L.append("None.")
    for x in t["check_differences"]:
        L.append(f"- `{x['trial_id']}`: mock {x['mock']['failed_checks']}, real {x['real']['failed_checks']}")
    L += ["", "## Not compared", ""]
    L += [f"- `{x['trial_id']}`: {x['why']}" + (f" ({real[x['trial_id']].get('error')})" if
          x["trial_id"] in real and real[x["trial_id"]].get("error") else "") for x in t["not_compared"]] or ["None."]  # fmt: skip
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
