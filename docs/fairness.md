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
- **opencode** (OpenCode + an OpenAI-compatible endpoint such as Nebius): skill folder `.opencode/skills/<name>/`, discovered natively and loaded through OpenCode's `skill` tool (verified locally against a scripted endpoint, see `docs/flagsmith-sdk-notes.md`). The skill is delivered the same way the official Agent Skills spec intends (a SKILL.md folder the agent discovers and the model chooses to load); nothing is pasted into the prompt.

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

Variant A (the official prompt, `prompt/OFFICIAL_PROMPT.md`) is unmodified. Only the skill (Variant B) changed. Each change below follows a fact verified live against a Flagsmith Cloud project (`docs/flagsmith-sdk-notes.md`):

- **Exact request bodies** for creating the flag, the keyed variation (project-level `features/` and `mv-options/` calls), the metric (`occurrence`/`up`, `definition.version 1`), the experiment (rollout body with the variation's option id) and `start/` (200, `running`) replace "take the shape from the docs or validation errors". These were exercised live and succeeded, and removing the doc-browsing step saves turns.
- **Branch on `.value`, not `.variant`**: live, the control bucket returns `variant='control'` while `value` carries the configured value, so `.variant` would not match the flag's values.
- **Python flush**: use `flush_events()` / `close()` with the default buffer. The skill no longer recommends `max_buffer_items=1` because repeated runs showed `get_experiment_flag` immediately followed by `track_event` drops the exposure with it (0/6 sent versus 6/6 with the default buffer plus `flush_events()`).
- **Events URL is separate from the API URL** (`events.api.flagsmith.com`, `events_api_url`/`eventsApiUrl`), as observed on the wire.
- **Warehouse** is auto-provisioned per environment live, so the skill treats it as a check, not a blocker.
- **Start before verifying**: exposures are only emitted while the experiment is running.
- **Token efficiency**: shortest happy path first, batch commands, no exploratory docs browsing unless a command fails, and stop with `DONE` after one successful verification. This is a length and ordering change aimed at agents with small turn budgets; it adds no experiment-specific content.

The skill remains neutral and reusable, with no reference to the study.

## Skill v2 (written after the primary results; exploratory)

Written on 2026-11-27, **after** the primary results and the failure analysis (`docs/failure-labels.md`) were known. Skill v2 (`skill/flagsmith-ab-test-v2/`, front-matter name still `flagsmith-ab-test`) was therefore designed with knowledge of how v1 failed. A follow-up comparison of v2 against the official prompt is **exploratory, not confirmatory**. The frozen v1 (`skill/flagsmith-ab-test/`) is preserved unchanged, so the primary experiment and the replication stay reproducible; the runner selects the folder with `HANDOFF_SKILL_DIR` (the `skill_dir` workflow input) and records it as `skill_dir` in every trial record. The official prompt, brief, grader, apps and agent configuration are untouched.

Each change is tied to failure-label evidence from the 220-trial primary run and to general SDK facts only (no harness-specific workaround):

1. **Exact import path per runtime** (browser/React `@flagsmith/flagsmith` and `/react`; Node `@flagsmith/nodejs`; Python `flagsmith`), with a warning that the `isomorphic` entry and an unbound `fetch` option passed to `init` silently lose events in browsers. Evidence: label 1, 10 failed React trials (9 isomorphic import, 1 `fetch: globalThis.fetch`); v1 snippets carried no import.
2. **One targeted docs read allowed** (the official run-an-experiment page, for the language tab) in place of "do not browse docs". Evidence: label 1 analysis; all 108 prompt-arm trials fetched the page and none used the isomorphic entry, 1 of 112 skill-arm trials did.
3. **Verification in the runtime that sends the events** (browser app: a headless-browser run observing the request to the events endpoint; server: hit the real route), one pass. Evidence: label 1, all 10 React failures verified only with a Node script that cannot show the browser failure.
4. **Flush guidance per runtime** (short-lived scripts and tests flush; servers and browsers rely on the SDK timer). `flushEvents` on `pagehide` is not mentioned because it is not verified in `docs/flagsmith-sdk-notes.md`.
5. **Kept** every v1 fact verified live: request bodies, `.value` versus `.variant`, the Python `max_buffer_items=1` pitfall, the separate events URL, start the experiment before verifying.
6. **Added** a short "events missing" troubleshooting line, and "call the experiment method on every page view; do not memoise its result" (label 10, one Node trial that added a 30 s cache). No caching layer is suggested.

Not addressed in v2, because they are harness or brief effects rather than skill-text gaps: label 2 (local evaluation, 4 trials) and label 3 (credentials at test import, 3 trials, corrected).

2026-11-27 extension: v2 is still unreleased and has not been tested as an experiment arm. It was extended with results reading against a pre-agreed decision rule, an approval-gated production ship step (`complete/` with `control` or `variant` plus the integer option id), rollout verification on fresh identities, and token-efficiency rules (`--json --jq`), to cover the whole job. These added steps (results reading, the ship step, rollout verification) were never run against live Flagsmith by an agent following the skill, so v2 is untested end to end. The extension adds no harness-specific content and still passes `skill/validate_skill.py`.

## Verified equal conditions (2026-11-27)

Checked from code and from all 440 trial records (`data/trials.jsonl` 220 primary, `data/replication.jsonl` 220 replication) plus the per-trial artifacts. Numbers are computed, not copied.

### (i) Tool and web access: identical, WebFetch available to both

- The variant is never an input to the agent command or its configuration. `OpenCodeBackend.build_command` takes only the model and `max_turns`; `build_config` takes only the model and environment; both ignore `variant`.
- Permissions are the one `PERMISSIONS` dict in `runner/agents/opencode.py`. Allowed: `bash`, `edit` (covers write), `read`, `glob`, `grep`, `webfetch`, `skill`. Denied: `list`, `websearch`, `task`, `todowrite`, `question`, `lsp`, `external_directory`, `doom_loop`. (`runner/config.py` `AGENT_TOOLS` = Bash, Read, Write, Edit, Glob, Grep, WebFetch, Skill is the equivalent list for the Claude backend, not used by these trials.)
- The `skill` tool is allowed in both arms. Only the skill arm has a skill installed (`prepare_workspace` copies it only for `variant == "skill"`), so the prompt arm's tool has nothing to load. Observed: the skill tool was called in 224/224 skill trials and 0/216 prompt trials.
- WebFetch was available and used in both arms. Observed: 216/216 prompt trials and 2/224 skill trials fetched a URL; the two skill fetches (`trial-45947370678-70`, `trial-45967764018-22`) were 404 or empty. The gap in use is behavioural: the official prompt leads agents to the docs, and skill v1 says "Do not browse docs or explore unless a command fails". That is part of what each handoff does, not a difference in access, but it means the arms differ in whether agents read the docs.
- Env isolation is the same for both: per-trial XDG dirs, no external skills, no Claude Code config (`OPENCODE_DISABLE_*`).

### (ii) Identical brief; only the handoff text differs

- `build_instruction` returns `head + separator + brief`, where `head` is the official prompt (prompt arm) or one fixed line (skill arm: "Set up a Flagsmith A/B test in this app using the flagsmith-ab-test skill."). The brief is the same rendered template; per-trial it differs only by the flag name.
- `brief_sha256` (hash of the raw template): 1 distinct value in each arm (`9b636f48ee6f...`, 216 prompt and 224 skill records). `prompt_sha256`: 1 distinct value in each arm (`506268c2ccc4...`). `skill_sha`: 1 distinct value in each arm (`eb5aa00e5679...`, frozen v1). In both arms across both stages.
- `grader_sha`: `3858b6bb4182` (first 40 primary trials, 20 per arm) and `746ccd2c5e86` (other 400, 196 prompt and 204 skill); the arms see the same graders in proportion. Repo commits: `c74e237` (20+20), `55184be` (88+92), `fa46bf2` (108+112), prompt+skill.

### (iii) SDK versions: NOT pinned in either arm (a limitation, not a defect)

Neither the brief, the prompt, the skill nor the sample apps pin an SDK version. Agents ran their own installs, so the version each trial got was whatever the registry served at install time. Lockfile evidence (`package-lock.json` additions in `diff.patch`; `docs/replication-gap.md` section 2) gives the resolved version:

| Stack | Package | Resolved (prompt arm) | Resolved (skill arm) |
|---|---|---|---|
| React | `@flagsmith/flagsmith` | 12.6.0 in 63/70 trials (7 added none) | 12.6.0 in 64/64 trials with a diff (2 also added `@flagsmith/nodejs` 9.5.0) |
| Node | `@flagsmith/nodejs` | 9.5.0 in 66/69 (3 added none) | 9.5.0 in 79/80 (1 none) |
| Python | `flagsmith` | `==6.7.0` in 72/77, `>=6.3.0` in 3, none in 2 (no lockfile) | `==6.7.0` in 73/79, `>=6.3.0` in 5, none in 1 (no lockfile) |

All three are the latest releases and were published on 2026-11-23 (npm registry `time` field and PyPI), before the first trial (2026-11-26 23:40 UTC). Both arms were interleaved in the same batches (assignment by Flagsmith bucketing), so they saw the same registry state; no trial resolved a different version. The declared ranges differed (caret ranges, a few older minimums), which could have mattered had a newer release appeared mid-study; none did. For the Python `>=6.3.0` cases the resolved version is not recorded, and PyPI's latest at the time was 6.7.0. The consequence is a reproducibility limit: a rerun after a new SDK release could differ.

### (iv) Same model, limits and agent version

All 440 records: `model` = `MiniMaxAI/MiniMax-M3.1-Flash`, `agent` = `opencode`, `agent_version` = 1.19.6, `max_turns` = 220, `max_tokens` = 12,000,000, `environment` = production, `assignment` = flagsmith, no dry runs, fake agents or skipped graders; one distinct value each, in both arms. The sampling temperature and seed are not set or recorded for either arm.
