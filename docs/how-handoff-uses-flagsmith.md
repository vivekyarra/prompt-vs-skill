# How Handoff uses Flagsmith

Flagsmith is the experiment engine of this project, not a logging side channel. It assigns every trial's variant, records the exposure, receives the grader's verdict as a conversion event, computes the statistics, and ships the winner with the same flag.

| Flagsmith feature | What we do | Where |
|---|---|---|
| Multivariate flag with a keyed variation | `onboarding_method`, control value `prompt`, variation `skill` with the key `skill`, 50/50. The key is what makes exposures recordable. | `ops/setup_experiment.py` |
| Experiment-flag read that records the exposure | The runner calls `get_experiment_flag("onboarding_method", trial ID, {"stack": ...})` before the agent starts. The call returns the variant and records the exposure in the same step. The runner branches on `.value`, because the control bucket reports `.variant == "control"`. | `runner/flags.py` (`SdkFlagsmithClient.get_exposure`) |
| `trackEvent` conversions | After grading, the runner sends `integration_verified` (all of C1 to C6 passed) and `over_budget` (a limit was hit) with the trial ID as identity, then flushes. The sample apps the agents modify use the same SDK calls (`trackEvent`, `track_event`). | `runner/flags.py` (`send_event`, `flush`), `runner/trial.py`, `apps/reference/` |
| Two metrics | `integration_verified` is the primary metric (occurrence, higher is better). `over_budget` is the guardrail (occurrence, lower is better). | `ops/setup_experiment.py` |
| Experiment with 50/50 assignment | One experiment per environment, 100% of trials enrolled, hypothesis and both metrics attached, started through the API. | `ops/setup_experiment.py`, `EXPERIMENT.md` |
| Traits | Each trial carries the trait `stack` (react, node, python) for the secondary breakdown. | `runner/flags.py` |
| Results, inference and the managed warehouse | Flagsmith computes exposures, conversion rates, lift, the credible interval and the chance to win from its managed warehouse. `ops/snapshot_results.py` takes an end-of-run snapshot, `analysis/analyze.py` renders it into `RESULTS.md`, and `analysis/crosscheck.py` compares Flagsmith's counts with our own log. They match exactly. | `ops/snapshot_results.py`, `ops/exp_counts.py`, `analysis/` |
| Late events | A conversion sent after the exposure still counts in the experiment, which allowed three corrected verdicts to be sent afterwards. | `ops/backfill_events.py`, `EXPERIMENT.md` |
| A second experiment on the same flag | The replication is a separate experiment on the same flag, with its own exposures and conversions. The old experiment is completed first and the new one is created with the same metrics and a 50/50 split. | `ops/rollover_experiment.py`, `ops/rolllib.py` |
| Ending an experiment and rolling out the winner | The winner is rolled out with the experiment's own rollout decision (`control` for the prompt, `variant` for the skill). Afterwards the runner reads the flag with a plain read and sends no events (`--assign rollout`). | `ops/rollout_winner.py`, `runner/flags.py` (`RolloutFlagsmithClient`) |
| The CLI and skills angle | The skill teaches an agent to set up this whole loop with the `flagsmith` CLI and the SDKs. The experiment measures how reliably an agent gets there from the official prompt versus from a skill. | `skill/flagsmith-ab-test/SKILL.md`, `skill/flagsmith-ab-test-v2/SKILL.md`, `prompt/OFFICIAL_PROMPT.md` |
| Two projects, scoped keys | The experiment project is touched only by the runner. Agents work in a separate sandbox project and create their own flags there, which the runner deletes after each trial. | `runner/cleanup_sandbox.py`, `docs/architecture.md` |

## Why this is a real use of experimentation

- The unit of analysis is the unit of assignment: one trial, one identity, one exposure.
- The decision rule (95% win probability, interval excludes zero, guardrail not worse) was fixed before the first trial (`EXPERIMENT.md`).
- Flagsmith's own inference is the primary result. Our Beta-Binomial analysis is a labelled cross-check.
- The same flag that ran the experiment is the one that ships the result.
