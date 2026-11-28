# Mock vs real Flagsmith: grader agreement (exploratory)

Exploratory check, declared in `EXPERIMENT.md` ("Declaration: mock vs real Flagsmith agreement check") and selection committed before any run. It does not change the primary decision, the replication result, any Flagsmith event of experiments 728 or 1142, or any `data/*.jsonl` trial record.

## Question

The grader judges every trial against a local Flagsmith emulator (`grader/mock.py`). Would the verdicts be the same if the agent's app talked to the real Flagsmith?

## Method

- **Selection** (`data/mock_vs_real_selection.json`, seed 20261128): all 28 trials recorded as failed in the primary and replication runs, plus 20 passing trials drawn from the 398 passing trials with a non-empty diff: 48 trials.
- **Replay:** as in `docs/regrade.md`: copy `apps/<stack>`, apply the saved diff, write env files for the names the added code reads. The only difference: key names get the real sandbox keys instead of placeholders.
- **Real backend:** in the sandbox project only, each trial's flag (same name; agent code hard-codes it) with control `Join` and option `Join free`, and a running 50/50 experiment `MVR <trial id>` on it, so the SDK experiment methods report `in_experiment` and send `$flag_exposure`. A pass-through HTTPS proxy (`ops/mvr_mitm_addon.py`) forwards every `*.flagsmith.com` request unchanged and records it with the real response in the emulator's record format (`scripts/mvr_lib.py`).
- **Judge:** the frozen `grader/checks.py` (tree `814c527`, unchanged), same stacks, browser visitors and 13 s waits. Real Flagsmith buckets identities by hash, so V1 and V2 can get the same value; then fresh visitors are added until one differs (the remedy `grader/cli.py` uses under local evaluation). Under local evaluation C6's expected value is what the real service evaluates for that identity.
- **Baseline (local emulator):** the offline emulator regrade of the same diffs with the same grader tree (`data/regrade_results.jsonl`). Run: `ops/mock_vs_real_regrade.py` through `ops.yml` (environment development, sandbox keys). Results: `data/mock_vs_real_results.jsonl`.

## Agreement

| group | trials | same verdict | same failed checks |
|---|---|---|---|
| overall | 47 | 46/47 (97.9%) | 45/47 (95.7%) |
| group=failing | 27 | 26/27 (96.3%) | 25/27 (92.6%) |
| group=passing_sample | 20 | 20/20 (100.0%) | 20/20 (100.0%) |
| stage=primary | 27 | 27/27 (100.0%) | 27/27 (100.0%) |
| stage=replication | 20 | 19/20 (95.0%) | 18/20 (90.0%) |
| variant=prompt | 15 | 14/15 (93.3%) | 13/15 (86.7%) |
| variant=skill | 32 | 32/32 (100.0%) | 32/32 (100.0%) |
| stack=node | 16 | 16/16 (100.0%) | 16/16 (100.0%) |
| stack=python | 8 | 8/8 (100.0%) | 8/8 (100.0%) |
| stack=react | 23 | 22/23 (95.7%) | 21/23 (91.3%) |

Agreement is with the emulator REGRADE, not with the recorded verdict: 12 of the 27 recorded failures pass on real Flagsmith, and 11 of those already pass in the emulator regrade (the 3 C1 corrections and the 8 local-evaluation trials of `docs/regrade.md`).

Per check (same pass/fail on the local emulator and on real Flagsmith; the declaration named C2-C6, all seven are shown):

| check | agree |
|---|---|
| C1 | 47/47 (100.0%) |
| C2 | 47/47 (100.0%) |
| C3 | 47/47 (100.0%) |
| C4 | 47/47 (100.0%) |
| C5 | 47/47 (100.0%) |
| C6 | 45/47 (95.7%) |
| C7 | 47/47 (100.0%) |

## Disagreements (verdict differs)

- `trial-45967760241-64` (replication, prompt, react): emulator fail C6, real pass; recorded fail.

## Same verdict, different failed checks

- `trial-45967755797-1`: emulator ['C1', 'C6'], real ['C1']

## Not compared

- `trial-45947367007-33`: no real verdict

## What the real service did

- Every Flagsmith response recorded was a success: `environment:200`, `events:202`, `flags:200`, `preflight:200` (kind:HTTP status). 46 of the 47 replays reached Flagsmith; `trial-45967760241-52` sent no request on either backend (it fails C2-C6 on both).
- 8 replays downloaded the real environment document and evaluated locally (the skill-arm Node trials flagged in `data/flagged.jsonl`).
- 23 replays needed extra visitors because real bucketing gave V1 and V2 the same value.

## Root cause of the C6 differences

Both C6 differences are prompt-arm React apps (replication) that choose the button text from the variant KEY, not the value: `flag?.variant === VARIANT_KEY ? VARIANT_LABEL : CONTROL_LABEL` with `VARIANT_KEY = 'join_free'` (the added lines are quoted per trial in `data/variant_key_audit.jsonl`). The emulator (`grader/mock.py`) returns synthetic keys `variant_0` / `variant_1`, so such an app always shows `Join` and fails C6 whenever the emulator serves `Join free`. Real Flagsmith returns the option's own key. This is a limitation of the emulator (a false fail), not of the apps. The real pass depends on the option key in the sandbox being `join_free`, the key this harness creates; it is also the key both agents created and documented in their own diffs. In `trial-45967755797-1` the verdict stays fail on both backends because C1 fails (its own test).

## How many trials does the variant-key gap touch? (exploratory)

`ops/variant_key_audit.py` (ops runs 46126189089, 46126191750) read the artifact of all 440 trials: 425 have a non-empty diff. 12 add a source line that compares something named `variant` (regex, tests and docs excluded; `data/variant_key_audit.jsonl`). In 10 of them the same code also reads the flag value (the comparison is a fallback, a diagnostic, or on the value itself). 2 choose the text from the variant key alone: `trial-45967755797-1`, `trial-45967760241-64`. Both were already in this sample. So, as far as a regex over added lines can tell, the gap touched no other trial, and exactly one recorded verdict is an emulator false fail: `trial-45967760241-64` (replication, prompt arm).

Sensitivity (exploratory, not a correction; Beta(1,1) Beta-Binomial from `analysis/analyze.py`, seed 20261129, denominators as in `docs/regrade.md`):

| view | prompt | skill | difference (skill-prompt), 95% CI |
|---|---|---|---|
| replication, regraded (docs/regrade.md) | 106/108 | 109/112 | -0.008 [-0.055, +0.038] |
| replication, regraded + the variant-key false fail counted as a pass | 107/108 | 109/112 | -0.018 [-0.062, +0.024] |
| both runs pooled, regraded (secondary, descriptive) | 214/216 | 209/224 | -0.058 [-0.096, -0.023] |
| both runs pooled, regraded + the variant-key false fail | 215/216 | 209/224 | -0.062 [-0.100, -0.029] |

The fix would favour the prompt arm by one trial and changes no conclusion. The recorded verdicts, the Flagsmith events and the pre-registered decision are not changed. Both known emulator limitations are now quantified: local evaluation (8 trials, skill arm, `docs/regrade.md`) and the variant key (1 trial, prompt arm).

## Runs

- Reported: ops workflow runs 46121487717, 46121490475, 46121493473, 46121496011 (shards 0-3 of 4, branch `claude/optimistic-tesla-chhr1a`, environment development, sandbox project only).
- Before: run 46119629420 failed at the first artifact download (auth header sent across the redirect), no verdict; run 46120467895 graded 4 trials as a smoke test (all pass, the same verdicts and failed checks as in the reported run). Fix between them: artifact download, Node pinned to 22 (the runner had 24).
- Sandbox objects: one flag and one experiment `MVR <trial id>` per trial in the sandbox Development environment (`development` is also the GitHub Actions environment name). No object, flag or event of the experiment project (experiments 728, 1142, 1058, 1414) was read or written.

## Limits

- Exploratory, one replay per trial on the real service (the emulator baseline had up to 3).
- The replay is not the original run: the agent's untracked env files are lost (see `docs/regrade.md`).
- Each replay uses a fresh sandbox flag and experiment, not the trial's original sandbox state.
- Real identity bucketing is random per identity; the emulator's is fixed. C6 is compared per identity.
