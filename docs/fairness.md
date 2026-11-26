# Fairness

The study compares two ways of handing a coding agent the job of setting up a Flagsmith A/B test: the official setup prompt (Variant A) and an Agent Skill (Variant B). Only the handoff method differs.

## Why a task brief is needed

The official prompt is written for an interactive session: it expects a human to answer questions (what to test, which project, which event) and to approve changes. Trials run headless, so no human is present. Without pre-answered questions, either variant could stall or guess. The task brief (`brief/TASK_BRIEF.md`) supplies those answers: what to test, the flag name, the success event, which Flagsmith project and which environment variable names hold credentials, blanket approval, and a ban on simulated traffic.

## Applied identically

The brief is identical word for word in both variants. The runner renders the same placeholders (such as `{{TRIAL_SUFFIX}}`) with the same logic for both. It is not tuned per variant.

## Delivery

- **Variant A (prompt):** instruction = the official prompt text (`prompt/OFFICIAL_PROMPT.md`, unedited), followed by the task brief.
- **Variant B (skill):** the skill `skill/flagsmith-ab-test/` is installed in the agent's project skill folder; instruction = one neutral line ("Set up a Flagsmith A/B test in this app using the flagsmith-ab-test skill."), followed by the task brief.

## Held constant

Same agent, same model, same tool permissions, same turn and token limits, same sample app pool, same environment, same credentials, same task brief. Specific values (model ID, limits) are fixed in the pilot and recorded in `EXPERIMENT.md`.

## Agent backends

The runner supports two agents, chosen once per experiment (`HANDOFF_AGENT`, or `--agent`); a single experiment must use one agent and one model for both variants.

- **claude** (default): Claude Code. Skill folder `.claude/skills/<name>/`, discovered natively.
- **opencode** (OpenCode + an OpenAI-compatible endpoint such as Nebius): skill folder `.opencode/skills/<name>/`, discovered natively and loaded through OpenCode's `skill` tool (verified locally against a fake endpoint, see `docs/verified-facts.md` section 9). The skill is delivered the same way the official Agent Skills spec intends (a SKILL.md folder the agent discovers and the model chooses to load); nothing is pasted into the prompt.

Held constant across backends: identical instruction text and task brief, the same capability set (shell, read, write/edit, glob, grep, web fetch, skill tool; everything else denied), the skill tool offered in BOTH variants, no global config or global skills read (per-trial config dirs, Claude/external skill discovery switched off for OpenCode), and the same limits enforced by the runner itself (turns counted from the event stream, tokens from reported usage, 30 minute wall clock; the process is killed on the first exceeded limit).

Caveats specific to the open-weight setup, to be stated next to any result:
- The system prompt, tool descriptions and skill-loading mechanism differ between Claude Code and OpenCode, and open-weight models differ from Claude in how reliably they decide to call the `skill` tool. A Variant B result on this setup measures "this model, in this harness, given this skill", not Claude Code.
- Token counts come from the provider's `usage` field. If the endpoint omits it, the token limit cannot trigger (the turn and time limits still do). The pilot must confirm usage is reported.
- `cost_usd` is computed from the prices the owner sets in `HANDOFF_PRICE_*`, billing all input tokens (cached ones included) at the input price, so it is an upper bound.
- The agent's shell can read the model API key from its environment (as with Claude). It cannot read the experiment key.

## Neutrality of the skill

The skill is written as a general, reusable skill. It contains no reference to the grader, the study, or any specific check. Its content is built from Flagsmith's published documentation.

## Limitations

The skill and the official prompt differ in length and content as well as format, so a result measures the packaged handoff as a whole, not any single ingredient.

## Skill revisions before the freeze (2026-11-26)

Variant A (the official prompt, `prompt/OFFICIAL_PROMPT.md`) is unmodified. Only the skill (Variant B) changed. Each change below follows a fact verified live against a Flagsmith Cloud project (`docs/verified-facts.md` sections 1.3 and 10):

- **Exact request bodies** for creating the flag, the keyed variation (project-level `features/` and `mv-options/` calls), the metric (`occurrence`/`up`, `definition.version 1`), the experiment (rollout body with the variation's option id) and `start/` (200, `running`) replace "take the shape from the docs or validation errors". These were exercised live and succeeded, and removing the doc-browsing step saves turns.
- **Branch on `.value`, not `.variant`**: live, the control bucket returns `variant='control'` while `value` carries the configured value, so `.variant` would not match the flag's values.
- **Python flush**: use `flush_events()` / `close()` with the default buffer. The skill no longer recommends `max_buffer_items=1` because the spike showed `get_experiment_flag` immediately followed by `track_event` drops the exposure with it (0/6 sent versus 6/6 with the default buffer plus `flush_events()`).
- **Events URL is separate from the API URL** (`events.api.flagsmith.com`, `events_api_url`/`eventsApiUrl`), as observed on the wire.
- **Warehouse** is auto-provisioned per environment live, so the skill treats it as a check, not a blocker.
- **Start before verifying**: exposures are only emitted while the experiment is running.
- **Token efficiency**: shortest happy path first, batch commands, no exploratory docs browsing unless a command fails, and stop with `DONE` after one successful verification. This is a length and ordering change aimed at agents with small turn budgets; it adds no experiment-specific content.

The skill remains neutral and reusable, with no reference to the study.
