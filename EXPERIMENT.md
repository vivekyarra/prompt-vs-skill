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
| Agent model ID | TBD (set in pilot) |
| Max turns (`HANDOFF_MAX_TURNS`) | TBD (set in pilot) |
| Max tokens (`HANDOFF_MAX_TOKENS`) | TBD (set in pilot) |
| Final sample target per variant | TBD (set in pilot) |
| Max parallel trials | TBD (set in pilot) |

## Freeze log

<!-- Append entries: timestamp (UTC), commit SHA, values frozen. -->
