# Why the replication gap shrank (investigation, 2026-11-27)

Question: the skill arm's React failures fell from 11/38 (primary) to 2/27 (replication) with the same model, skill v1 and (post-fix) grader, and the replication interval crossed zero. Everything below is computed from `data/trials.jsonl`, `data/replication.jsonl`, `data/corrections.jsonl` and the per-trial artifacts (`diff.patch`, `agent_output.jsonl`). No raw data was edited.

## Pooled 440 trials (SECONDARY, not the decision)

Beta(1,1) Beta-Binomial, 100,000 draws, seed 20261129, via `analysis/analyze.py` (`beta_binomial_diff`, `beta_interval`). Difference = skill - prompt; brackets are 95% credible intervals. The primary and the replication are different runs with different heterogeneity, so pooling is descriptive only.

| View | prompt | skill | diff (95% interval) |
|---|---|---|---|
| as graded, runner error counted as fail | 213/216 = 98.6% | 199/224 = 88.8% | -0.097 [-0.144, -0.054] |
| as graded, runner error excluded | 213/216 | 199/223 = 89.2% | -0.093 [-0.139, -0.050] |
| as corrected (3 backfilled), runner error excluded | 214/216 = 99.1% | 201/223 = 90.1% | -0.088 [-0.133, -0.049] |
| as corrected, runner error counted as fail | 214/216 | 201/224 = 89.7% | -0.092 [-0.138, -0.052] |

Flagsmith's primary counts (prompt 108/108, skill 96/112) already include the 3 backfilled corrections; as graded they are 107/108 and 94/112. Replication needed no corrections (106/108, 105/112).

## 1. Counts verified

| | primary prompt | primary skill | repl. prompt | repl. skill |
|---|---|---|---|---|
| react | 0/36 | 11/38 | 2/34 | 2/27 |
| node | 1/39 | 5/41 | 0/30 | 4/39 |
| python | 0/33 | 2/33 | 0/44 | 1/46 |
| all (failures/n, as graded) | 1/108 | 18/112 | 2/108 | 7/112 |

- The "16/112" skill figure is the corrected primary (18 minus 2 corrected Python C1 failures). As graded it is 18/112. Of the 11 primary skill React failures, 1 (`trial-45947367007-33`) is a runner error (`UnicodeDecodeError` while reading agent output; never graded, no diff). Graded React failures: 10/37.
- Whole drop is React: node 5/41 -> 4/39 and python 2/33 -> 1/46 are flat.
- Post-fix 180-trial subset (commit 55184be): skill 13/92 (React 9/26, node 4/36, python 0/30), prompt 0/88.
- Replication prompt arm failed 2 React trials (0/36 in primary): one with no Flagsmith traffic at all, one C6 (UI did not render the flag value).
- The arms were not stack-balanced: skill React n is 38 vs 27, an artefact of random stack assignment.

## 2. (a) Resolved SDK versions: no change

Parsed from the lockfile/manifest lines of every `diff.patch` (one trial has no diff). Every trial that installed an SDK resolved the same version in both runs and both arms: `@flagsmith/flagsmith` 12.6.0 (React), `@flagsmith/nodejs` 9.5.0 (Node), `flagsmith` ==6.7.0 (Python, from requirements; a few wrote `>=6.3.0`). Declared ranges varied (`^12.6.0` mostly, `^12.4.0` in 2+2 prompt trials, `^9.1.0` in 3+4 prompt trials) but resolved identically. npm and PyPI data confirm these were the latest releases and published before any trial: `@flagsmith/flagsmith` 12.6.0 on 2026-11-23, `@flagsmith/nodejs` 9.5.0 on 2026-11-23, PyPI `flagsmith` 6.7.0 on 2026-11-23 (trials ran 2026-11-26 23:40 to 2026-11-27 10:47 UTC). Versions were unpinned but nothing changed during the study. Not an explanation.

## 3. (b) Import entry point and docs fetching

Skill-arm React trials, by import of the Flagsmith instance (`iso_only` = imports `/isomorphic`, never the plain `@flagsmith/flagsmith` default):

| | iso_only (fail/n) | iso + plain (fail/n) | no isomorphic (fail/n) |
|---|---|---|---|
| primary (37 with diff) | 9/10 | 0/5 | 1/22 |
| replication (27) | 1/1 | 0/4 | 1/22 |

- 9 of the 10 graded primary failures are the known isomorphic-import failure (events silently lost in the browser); the rate of `iso_only` fell from 10/37 to 1/27 (Fisher p=0.018, exploratory, chosen after seeing the data). Failure given `iso_only` is the same in both runs (9/10, 1/1); failure without it is the same (1/27, 1/26). So the gap is entirely "how often the agent picked `/isomorphic`".
- In all 65 skill React trials the agent listed `node_modules/@flagsmith/flagsmith` and read its package.json, so the `isomorphic` entry was visible in both runs.
- Docs: all 108+108 prompt-arm trials called WebFetch (all 3 stacks) and none used `/isomorphic`. The skill arm fetched docs in 1/112 trials per run (node; both were 404 errors) because skill v1 says "Do not browse docs". Both arms have WebFetch; the handoff text changes whether it is used.
- The per-run `iso_only` rate varies a lot inside the primary: 0/4, 2/8, 0/2, 2/6, 6/17 (by run), then 1/6, 0/9, 0/12 in the replication.

## 4. (c) Did the docs page change?

Prompt-arm agents fetched `https://docs.flagsmith.com/experimentation/run-an-experiment` 217 times; 214 returned byte-identical text (sha256 prefix 20ca6c84c6dc) across all 8 runs from 23:40 to 10:47 UTC, 3 returned a differently formatted rendering (809bf32736f8, 2 primary and 1 replication). The React-tab snippet (`import flagsmith from '@flagsmith/flagsmith'; import { FlagsmithProvider } from '@flagsmith/flagsmith/react'`) matches the current live page verbatim; neither contains "isomorphic". The rest of the live page is HTML-rendered and cannot be compared byte for byte. Only the prompt arm read it, so it cannot explain a skill-arm change in any case.

## 5. (d) Timing, batches, concurrency, order

- Trial start times are `timestamp_utc`; concurrency is estimated from start and `duration_s`. Max overlap was 5 (runs 45912277670, 45914099371, 45925699686), 10 (the two 80-trial runs together), 15 (replication).
- Skill React failures by run: 0/4, 2/8, 0/2, 3/7, 6/17 (primary); 1/6, 1/9, 0/12 (replication). At concurrency 5: 2/14; at 10: 9/24; at 15: 2/27. Not monotone in load, so load is not a clean explanation either way (and confounded with date and run).
- By hour of day (UTC, skill React fail/n): primary 00h 2/8, 02h 0/2, 05h 1/3, 06h 5/10, 07h 2/8, 08h 1/3, 23h 0/4; replication 08h 0/2, 09h 2/14, 10h 0/11. The worst hour (06h) is inside the primary; no pattern that survives the small counts.
- Run order: failures are spread across start-order terciles (e.g. 2/2/2 in run 45947370678); no concentration in particular indexes.

## 6. (e) Code differences, read hunk by hunk

`git diff 55184be fa46bf2 -- grader skill prompt brief apps` is empty. Under `runner/` 11 files differ (508 insertions): (i) `errors="replace"`/`encoding="utf-8"` on subprocess and file reads (`agent.py`, `agents/base.py`, `grader_step.py`, `workspace.py`): the fix for the one primary runner error; (ii) `stage` field, `resolve_stage`, rollout assignment mode (`config.py`, `cli.py`, `flags.py`, `trial.py`), used only for records or `assign=rollout`; (iii) record-only `skill_tool_calls`, `skill_loaded`, `flag_exists_at_cleanup` (`skill_usage.py`, `trial.py`, read-only admin API GET in the cleanup `finally`); (iv) `trials.yml` gains a `stage` input; (v) tests. `build_instruction`, the skill install, tools and permissions, limits and the agent environment are unchanged. None of these can change what the agent sees or how a trial is graded.

`git diff c74e237 55184be -- grader`: `stacks.py` `app_tests` now re-runs a failed existing test once with the placeholder credential variables (a C1 fallback that can only turn a fail into a pass), `cli.py` passes the flag name to it, `checks.py` changes only the C1 detail string. It affects the first 40 primary trials' C1 only (the 3 corrections); every React failure is C2/C3/C4. Grader tree sha is `746ccd2` for the last 180 primary and all 220 replication trials.

## 7. (f) Sampling variation: exact two-sided Fisher (stdlib)

Skill arm, failures/n:

| comparison | counts | p |
|---|---|---|
| all stacks, primary as graded vs replication | 18/112 vs 7/112 | 0.032 |
| all stacks, primary corrected vs replication | 16/112 vs 7/112 | 0.076 |
| React, primary vs replication | 11/38 vs 2/27 | 0.057 |
| React, primary graded only (runner error dropped) | 10/37 vs 2/27 | 0.058 |
| all stacks, post-fix 180 vs replication | 13/92 vs 7/112 | 0.096 |
| React, post-fix 180 vs replication | 9/26 vs 2/27 | 0.019 |
| node / python, primary vs replication | 5/41 vs 4/39; 2/33 vs 1/46 | 1.0; 0.57 |
| prompt arm, primary vs replication (all; React) | 1/108 vs 2/108; 0/36 vs 2/34 | 1.0; 0.23 |

These are unplanned post-hoc tests, uncorrected for multiplicity; the post-fix React row is a selected subset. Within the replication, skill vs prompt: 7/112 vs 2/108 (p=0.17), React 2/27 vs 2/34 (p=1.0).

## 8. (g) Other observations

- Records are identical on model, agent version, limits, brief, prompt and skill hashes (see `docs/fairness.md`). All 440 flag names are unique; none overlap between runs.
- Effort (excluding the runner-error trial; median / p90). Turns: primary prompt 80/119, skill 58/89; replication prompt 80/125, skill 57/91. Total tokens (thousands): primary prompt 4130/7110, skill 2020/5020; replication prompt 4060/7580, skill 2280/4790. Cost per trial ($): primary prompt 0.090/0.166, skill 0.052/0.163; replication prompt 0.088/0.169, skill 0.063/0.137. Duration (s): primary prompt 500/767, skill 207/720; replication prompt 470/730, skill 227/748.
- Passing trials only: primary skill turns 55.5/86, tokens 1860/4910, cost 0.049/0.133, duration 177/629; replication skill 57/87, 2250/4750, 0.062/0.131, 213/730; prompt arms are unchanged from the all-trials figures to within about 2%. Failing is not cheap: pooled failing skill trials have medians 72.5 turns, 3460K tokens, $0.098 and 523 s versus 56, 2070K, $0.053 and 205 s for passing ones. Skill-arm effort is stable between runs; the skill arm is cheaper than the prompt arm by roughly half in tokens and in time, in both runs.
- Skill React effort in the replication is similar to the primary (mean 72 turns vs 73).

## What we can and cannot say

- **Most likely explanation, about 70% confidence: sampling variation in a stochastic agent.** The failure mechanism is a single behaviour (choosing `/isomorphic`), and its frequency was highly variable even between primary runs (0/4 to 6/17). Under the observed per-run spread, 1/27 in the replication is not remarkable. Nothing checked differs between runs: SDK versions, docs text, inputs, runner behaviour, grader, skill and brief are the same, and failures do not track hour, order or load.
- **Not excluded, about 20%: a change in the model endpoint or serving behaviour** (the model is MiniMax-M3.1-Flash behind an OpenAI-compatible API; no seed or temperature is recorded). This cannot be tested from the data. Residual about 10%: a real but small effect of something not recorded.
- **Unexplained:** why the `iso_only` rate fell from 27% to 4%; the 2 prompt-arm React failures in the replication (no mechanism shared with the skill ones).
- **Implication for the primary result:** the primary (-0.132 corrected, interval [-0.204, -0.071]) and the replication (-0.043, [-0.102, +0.011]) differ; the skill-arm failure rates differ at Fisher p=0.032 as graded and p=0.076 corrected. That is moderate evidence of between-run variation, not a demonstrated cause. The honest reading is that the skill v1 arm was worse than the prompt arm in the primary and not distinguishably worse in the replication, with the pooled secondary estimate at about -0.09 and an interval excluding zero. The direction held in both runs, but the size is uncertain and the primary's magnitude may be an overestimate.
