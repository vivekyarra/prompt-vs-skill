# Offline regrade of the 440 saved agent diffs with the final grader

Written in two steps. Method and counting rule first (this part was fixed before any regrade output was read); results after.

## Method

- Inputs: `diff.patch`, `trial_record.json`, `grader_result.json` of the 440 trial artifacts (primary runs 45912277670, 45914099371, 45925699686, 45947367007, 45947370678; replication runs 45967764018, 45967760241, 45967755797).
- `scripts/regrade_diffs.py` copies `apps/<stack>`, applies the diff, and runs the final grader as the runner did: `--mode proxy --reclaim-port`, flag name of the trial, default 13 s waits. `.github/workflows/regrade.yml` fans this out over 20 `ubuntu-latest` shards (Python 3.12, Node 22, Playwright chromium, mitmproxy) on a push to `regrade/run1`; an aggregate job merges the shards into `regrade_results.jsonl`.
- The agent's untracked `.env` / `.env.local` are not in the diffs (`git add -A` honours the agent's `.gitignore`). For every env name that code added by the diff reads (`import.meta.env.X`, `process.env.X`, `os.environ["X"]`, `os.getenv("X")`, ...) and that the grader does not itself supply, the script writes a placeholder into `.env` and `.env.local`: key-like names (`*_KEY`, `*_TOKEN`, `*ENVIRONMENT*`) get a placeholder key (`ser.` for node/python, client key for react), flag-like names get the trial's flag name; URLs, `DEBUG`, `DISABLED` and the like are not supplied, so the app's own default applies. Files cannot be replaced by real environment variables for `FLAGSMITH*` names: the grader strips those from the app's environment by design.
- Nothing is sent to Flagsmith, no event is created or altered, no `data/*.jsonl` record is edited. The output (`data/regrade_results.jsonl`, `data/regrade_summary.json`) is new data.
- A trial whose regrade verdict differs from the original is regraded twice more (three runs in total).

## Counting rule (fixed in advance)

A trial's ORIGINAL verdict stands unless ALL of these hold: (1) the regrade verdict differs, (2) the cause is one of the two named grader changes: the C1 test-environment fix, or the environment-document emulator, and (3) the difference reproduces in 3 of 3 runs. Every other disagreement is LISTED and explained but not counted. Pass-to-fail flips are reported as prominently as fail-to-pass flips.

- Cause C1 fix: the original failed C1 and the regrade passes C1 (only the 40 trials graded before that fix, grader tree `3858b6b`, can have it).
- Cause environment document: the regrade result has the `local_evaluation` block (the app downloaded the environment document).
- Agreement is computed FIRST, on the trials NOT flagged as local evaluation (`data/flagged.jsonl`), as the share whose regrade verdict equals the original. Poor means below 95% (the 3 documented C1 corrections in `data/corrections.jsonl` are expected to differ and are left out of that rate; they are still listed). If it is poor, the offline replay is not faithful for those trials and the sensitivity table is NOT built from it; what can be reported is reported.

## Results

(pending)
