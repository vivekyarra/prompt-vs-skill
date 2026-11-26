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
| Agent (`HANDOFF_AGENT`) | TBD (set in pilot): `claude` (Claude Code) or `opencode` (OpenCode + Nebius, see `docs/verified-facts.md` section 9) |
| Agent model ID | TBD (set in pilot; for `opencode` the exact Nebius model id from `GET /v1/models`) |
| Model prices per 1M tokens (`HANDOFF_PRICE_IN_PER_M`, `HANDOFF_PRICE_OUT_PER_M`) | TBD (set in pilot; used only to compute `cost_usd` when the agent CLI reports none) |
| Max turns (`HANDOFF_MAX_TURNS`) | TBD (set in pilot) |
| Max tokens (`HANDOFF_MAX_TOKENS`) | TBD (set in pilot) |
| Final sample target per variant | TBD (set in pilot) |
| Max parallel trials | TBD (set in pilot) |

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

## Grader corrections found in the pilot

(The pre-registered table above is unchanged.)

- **2026-11-26, grader wait bug.** All three Flagsmith SDKs flush buffered events on a 10 s timer, but the grader waited
  only 3 s after load and 5 s after the click (the spec defaults), so correct integrations without an explicit flush were
  wrongly failed on C3/C4. The grader now waits 13 s (10 s flush interval + 3 s margin) in every browser phase
  (`--load-wait` / `--click-wait`, still overridable). This deviates from the spec's 3 s / 5 s waits for this reason.
  The C1-C6 pass conditions are UNCHANGED. Details: `docs/grader.md`; pilot re-grade: `docs/pilot-regrade.md`.

## Scope of `integration_verified` (read before interpreting results)

The grader judges runtime behaviour from network traffic. It answers all `*.flagsmith.com` requests
itself and always reports the trial's flag as enrolled in a running experiment. Therefore a trial can
pass without the agent having created the flag, keyed variation, metric or experiment in Flagsmith: the
metric means "the code the agent wrote is wired correctly (experiment-flag read, exposure, conversion on
click, same stable identity, UI driven by the flag)". It does not verify the Flagsmith-side setup.
Any finding about Flagsmith-side setup would need a separate check against the sandbox project.
