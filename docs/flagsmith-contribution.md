# Flagsmith contribution (DRAFT, issue template)

A human reviews and posts this (H9). Every field marked TBD is filled from `RESULTS.md` and the Flagsmith dashboard only after real data exists. Do not post with TBD fields.

---

**Title:** Experiment results: official setup prompt vs Agent Skill for onboarding coding agents (TBD - result summary)

## Question

Does an Agent Skill get coding agents to a correctly wired Flagsmith experiment more often than Flagsmith's official setup prompt?

## Method

- Flag: `onboarding_method` (multivariate: `prompt` control, `skill` variation), 50/50, identity = trial ID.
- One trial = one headless Claude Code run on one sample app (React, Node, Python), same model, tools, limits and task brief in both variants.
- Primary metric: `integration_verified`, sent only when a grader passes checks C1-C6 from recorded network traffic.
- Guardrail: `over_budget`.
- Sample size: TBD per variant.
- Decision rule (pre-registered in `EXPERIMENT.md`): ship the winner only if win probability >= 95% AND the credible interval on the difference excludes zero AND the guardrail is not significantly worse; otherwise inconclusive.

## Result

| Field | Value |
|---|---|
| Exposures (prompt / skill) | TBD |
| `integration_verified` rate (prompt / skill) | TBD |
| Credible interval on the difference | TBD |
| Win probability | TBD |
| Guardrail `over_budget` (prompt / skill) | TBD |
| Decision | TBD (ship / inconclusive) |
| Read from Flagsmith dashboard at (UTC) | TBD |

## Most common failure modes per variant

From `RESULTS.md` section 5 (per-check failure rates C1-C6):

- Prompt: TBD
- Skill: TBD

## Suggestions

Each suggestion must be tied to an observed failure.

1. TBD - suggestion for the official prompt, tied to failure: TBD
2. TBD - suggestion for the skill, tied to failure: TBD

## Offer

TBD - if the skill won: an offer to contribute it to the official skills repo.

## Links

- Repo: https://github.com/vivekyarra/prompt-vs-skill
- Results: `RESULTS.md` in the repo
- Pre-registration: `EXPERIMENT.md` in the repo
