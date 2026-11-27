# Pre-registered experiment

These values are fixed before any real trial runs. Only items marked "set in pilot" may be filled in after the pilot, and they must be frozen and committed before the full run.

| Item | Value |
|---|---|
| Question | Does an Agent Skill get coding agents to a correctly wired Flagsmith experiment more often than Flagsmith's official setup prompt? |
| Hypothesis | Agents given the Agent Skill pass the grader more often than agents given the official prompt, without exceeding the budget more often. |
| Unit | One trial = one agent run on one sample app |
| Identity | The trial ID (`trial-<run_id>-<index>`), unique per trial, used for every Flagsmith call about that trial |
| Flag | `onboarding_method`, multivariate. Control value `prompt`, variation `skill` (with a key, so exposures are recorded) |
| Split | 100% of trials enrolled, 50/50 |
| Exposure | Recorded when the runner calls the experiment-flag method with the trial ID, before the agent starts |
| Primary metric | `integration_verified` (occurrence, higher is better). Sent only when the grader passes all primary checks (C1–C6) |
| Guardrail metric | `over_budget` (occurrence, lower is better). Sent when the agent hits the turn limit or token limit |
| Trait | `stack` = `react`, `node`, or `python` (for secondary breakdown only) |
| Sample target | 150–200 trials per variant (final number set in pilot, see Phase 9) |
| Decision rule | Ship the winning variant only if Flagsmith reports ≥95% win probability for it AND the credible interval on the difference excludes zero AND the guardrail is not significantly worse for it. Otherwise report the result as inconclusive and state roughly how many more trials would be needed. |
| Stopping rule | Do not stop when the result looks good. Stop only when the target sample is reached or the deadline buffer (29 Nov, 12:00 IST) is hit, whichever comes first. |
| Sanity check | Sample ratio check: exposures per variant must be within roughly 45/55. A larger imbalance means a bug; pause and fix before trusting any result. |
| Fairness | Same agent, same model, same tool permissions, same turn and token limits, same sample app pool, same task brief. The only difference between variants is the handoff method. |

## Set in pilot (TBD)

| Item | Value |
|---|---|
| Agent (`HANDOFF_AGENT`) | `opencode` (OpenCode 1.19.6 + Nebius Token Factory; see `docs/verified-facts.md` section 9). Frozen 2026-11-27. |
| Agent model ID | `MiniMaxAI/MiniMax-M3.1-Flash` (chosen from the screening below on the pooled pass rate only; the only candidate that was neither at the floor nor unusable) |
| Model prices per 1M tokens (`HANDOFF_PRICE_IN_PER_M`, `HANDOFF_PRICE_OUT_PER_M`) | input $0.15, output $0.60; cache reads $0.015 (Nebius listing, preflight 2026-11-26). The recorded `cost_usd` uses cache-read pricing; the full-price upper bound is about 6x higher on input |
| Max turns (`HANDOFF_MAX_TURNS`) | 220. The plain 1.5x p90 rule was unusable: the first pilot at 60 turns hit the cap on 10/10 trials. At a 200-turn cap every trial ended on its own (turns 59-161, p90 about 146), and 1.5x p90 is about 220 |
| Max tokens (`HANDOFF_MAX_TOKENS`) | 12,000,000 (1.5x the p90 of about 7M total tokens; the largest successful pilot run used 8.3M) |
| Final sample target | **220 trials total** (about 110 per variant; below the 150-200 per variant in section 2: a budget deviation, see the Pilot section). Fixed: N = min(400, ($35 - $9.5 recorded spend) / (1.5 x $0.076 mean cost of the final Development batch)) = 223, rounded down to 220 |
| Max parallel trials | 5 (`trials.yml`; the pilots ran 10 concurrent jobs with no rate-limit errors) |

## Pilot (Development, 2026-11-26/27): what was run and what was chosen

All pilot trials used the Development environment and are excluded from the experiment (`analysis/analyze.py` only
reads production records with Flagsmith assignment; collect.yml writes everything else to `data/pilot.jsonl`).
Models were screened on the **pooled pass rate only, never on the gap between arms**.

| Model | Trials | Pooled pass (recorded) | Mean cost/trial | Note |
|---|---|---|---|---|
| MiniMaxAI/MiniMax-M3.1-Flash | 30 (3 batches) | 19/30 recorded; 28/30 (93.3%) after grader corrections (see below) | about $0.08 (cache-read pricing) | chosen. First batch ran at a 60-turn cap and was censored |
| Qwen/Qwen3-30B-A3B-Instruct-2507 | 10 | 0/10 | $0.57 (loops to the turn/token limit) | floor; $5.74 spent |
| nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 10 | 0/10 | $0.04 | floor |
| nvidia/nemotron-3-super-120b-a12b | 8 | 0/8 | $0.05 | floor |
| openai/gpt-oss-120b | 8 | not scored | $0 | agent never ran under OpenCode (provider error "Expected 'id' to be a string"); the runner now records such trials as `runner_error` |

Spend recorded across all pilots: about $8.6 of the owner's Nebius balance (reported as $57.69 before the pilots).

**Ceiling warning (stated before the run):** with the chosen model both arms are expected to pass about 90% or more.
At that level a true difference smaller than roughly 10 percentage points will most likely be reported as
**inconclusive** at our sample size. This is accepted; the failure-mode analysis stands either way.

**Secondary outcomes, outside the decision rule:** turns, tokens, cost and duration per arm.

**Inference fallback:** Flagsmith returned `inference: null` for the Development pilot. If it is still null at the end
of the production run, the decision rule is applied using our own Beta-Binomial analysis (`analysis/analyze.py`),
clearly labelled as ours and not Flagsmith's.

**Budget deviation:** the owner's instruction was to work autonomously within the Nebius balance; the working cap is
$35 of recorded spend. The sample target is set from the measured cost of the final Development batch (see Freeze log)
and may fall below the 150-per-variant target in section 2; that shortfall is a budget deviation, not a change to
the pre-registered table.

## Flagsmith object IDs (not secrets)

| Object | Value |
|---|---|
| Experiment project | `handoff-experiment`, id 56666, org "Yarra's Org" |
| Experiment environments | Development id 121204, Production id 121205 |
| Sandbox project | `handoff-sandbox`, id 56668, org "Handoff Sandbox" (42328); envs Development 121208, Production 121209 |
| Flag `onboarding_method` | id 306199 (project-level, MULTIVARIATE, control `prompt`, variation `skill` option id 37439 with key `skill`, 50/50) |
| Warehouse connections | Development 13187, Production 13188 (`flagsmith` type, auto-provisioned) |
| Metrics, Development | `integration_verified` 744, `over_budget` 745 |
| Metrics, Production | `integration_verified` 747, `over_budget` 748 |
| Experiment "Handoff pilot" (Development) | id 727, running since 2026-11-26T19:37Z |
| Experiment "Handoff: Prompt vs Skill" (Production) | id 728, running since 2026-11-26T19:36:48Z, 100% rollout, 50/50 |
| Dashboard link | `https://app.flagsmith.com/project/56666/environment/<env key>/experiments/<id>` |

Note: Development pilot data contains a few `setup-check-*` identities (see `docs/verified-facts.md` section 10); exclude them from analysis.

## Freeze log

<!-- Append entries: timestamp (UTC), commit SHA, values frozen. -->

- **2026-11-27, before any production trial.** Code frozen at commit `b056fb14a4d8a3dd9b07cf8e1fd5ade4401bd7e5`
  (branch `feat/pilot-fixes`), tested by a final Development batch of 12 trials with real Flagsmith assignment and
  bare workflow defaults (run 45907896688): 11/12 passed, 0 runner errors, mean cost $0.076, every record carried
  `model=MiniMaxAI/MiniMax-M3.1-Flash`, `max_turns=220`, `repo_sha=b056fb1`. The one failure (skill arm, React) was
  diagnosed as an agent bug (it passed `fetch: globalThis.fetch` into the SDK options, which stops event delivery;
  removing that line makes C2-C7 pass), not a harness artefact. Frozen values: agent `opencode` 1.19.6, model
  `MiniMaxAI/MiniMax-M3.1-Flash`, 220 turns, 12,000,000 tokens, prices $0.15/$0.60 per 1M, max parallel 5,
  N = 220 trials, grader waits 13 s, pass rule C1-C6 unchanged, skill and official prompt as in this commit.
  The merge to `main` is a squash of the same tree; only documentation files changed after the tested commit.
- **Deviation (2026-11-27, after 40 production trials): grader test-environment bug.** The grader ran the app's
  existing test (C1) without the fake credential variables it supplies at app start, so apps that read their key
  from the environment at import time were failed for that alone. Found by reading the C1 failures of production
  run 45914099371. The fix is one-directional: the test runs in the clean environment first, and only a failing
  run is retried with the fake variables, so no earlier pass can change. Three trials flipped (replayed 3 times
  each with the final grader; see `docs/pilot-regrade.md`): `trial-45914099371-14` (skill, python),
  `trial-45914099371-7` (skill, python), `trial-45914099371-30` (prompt, node), all originally C1 failures.
  Per-arm rates for the first 40 trials had already been seen when this was decided. Rule applied: only these C1
  verdicts are corrected (`data/corrections.jsonl`); `integration_verified` for them is sent afterwards with
  `ops/backfill_events.py` (late events were verified to be counted in Development: a conversion for an identity
  exposed hours earlier raised the conversion count 8 -> 9). RESULTS.md reports results **as originally graded
  and as corrected**, and with and without the first 40 trials.
- **Diagnosed, not corrected (2026-11-27):** the other three failures of that batch (`docs/production-failure-diagnosis.md`):
  trials 11 and 20 (skill, React) are agent mistakes (the SDK's isomorphic entry used in a browser loses all
  events); trial 12 (skill, node) is a **grader limitation**: the agent enabled local evaluation (triggered by the
  `ser.` prefix of the grader's fake server key) and the mock does not implement the environment-document
  endpoint. It is not corrected: whether a real environment document carries experiment enrolment is unverified,
  so counting it as a pass would be a guess. It stays a failure and is flagged here and in RESULTS.md. The skill's
  single verification step runs in Node, which cannot catch the browser-only bug; this is reported as an observation
  about the frozen skill, not changed.
- **Production batching plan:** the first production batch is 10 trials, then a count cross-check against
  Flagsmith, then batches up to 40 trials in total, then a pause until the owner has read the Nebius balance
  (predicted spend is recorded alongside) before the remaining batches. The stopping rule is unchanged: stop at
  220 trials or at 29 Nov 12:00 IST, whichever is first; the win probability is not read to decide.

## Grader corrections found in the pilot

(The pre-registered table above is unchanged.)

- **2026-11-26, grader wait bug.** All three Flagsmith SDKs flush buffered events on a 10 s timer, but the grader waited
  only 3 s after load and 5 s after the click (the spec defaults), so correct integrations without an explicit flush were
  wrongly failed on C3/C4. The grader now waits 13 s (10 s flush interval + 3 s margin) in every browser phase
  (`--load-wait` / `--click-wait`, still overridable). This deviates from the spec's 3 s / 5 s waits for this reason.
  The C1-C6 pass conditions are UNCHANGED. Details: `docs/grader.md`; pilot re-grade: `docs/pilot-regrade.md`.

- **2026-11-27, C1 test environment (found after the 40 production trials).** The app's existing test ran in a clean
  env without the fake credential variables the grader supplies at app start, so apps that read their key from the
  environment at import time failed C1 spuriously (3 of 40 trials). The test now runs clean first and, only if that
  fails, is re-run once with the fake keys (pass if that passes). One-directional: a clean pass is never turned into a
  fail. C1-C6 pass conditions are UNCHANGED. Details: `docs/grader.md`; replays: `docs/pilot-regrade.md`.

- **Known limitation (C6).** The mock Flagsmith returns a fixed variant key and the value `Join free`; an integration that
  branches on the variation KEY (e.g. `flag.variant === 'Join_free'`) instead of the flag VALUE cannot be verified and is
  scored as failing C6 (observed in one pilot trial, prompt arm, React). C6's pass condition is unchanged.

## Scope of `integration_verified` (read before interpreting results)

The grader judges runtime behaviour from network traffic. It answers all `*.flagsmith.com` requests
itself and always reports the trial's flag as enrolled in a running experiment. Therefore a trial can
pass without the agent having created the flag, keyed variation, metric or experiment in Flagsmith: the
metric means "the code the agent wrote is wired correctly (experiment-flag read, exposure, conversion on
click, same stable identity, UI driven by the flag)". It does not verify the Flagsmith-side setup.
Any finding about Flagsmith-side setup would need a separate check against the sandbox project.
