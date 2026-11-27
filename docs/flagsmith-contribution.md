<!--
Ready to post as a GitHub issue on the Flagsmith docs/skills repository. Numbers come from RESULTS.md (primary stage only).
-->

**Title:** We ran Flagsmith's setup prompt against an Agent Skill as a real Flagsmith experiment: 108/108 vs 96/112, plus the fixes that close the gap

## Summary

We measured which handoff gets a coding agent to a correctly wired Flagsmith A/B test more often: the official setup prompt ([Set up with a coding agent](https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent)) or an Agent Skill we wrote from Flagsmith's published docs. We ran it as a pre-registered Flagsmith experiment with 220 real agent runs, and Flagsmith assigned the variants, recorded the exposures and computed the result.

| | Official prompt | Agent Skill (v1) |
|---|---|---|
| Trials | 108 | 112 |
| `integration_verified` | **108 (100%)** | 96 (85.7%) |
| Guardrail `over_budget` | 1 | 1 |

Flagsmith's own inference: lift -14.3% for the skill, credible interval [-0.208, -0.078] on the absolute difference, skill chance to win about 0.0009%. Our own log matches Flagsmith's exposure and conversion counts exactly. The official prompt currently gets agents to a correctly wired experiment more often, and the failure analysis shows exactly why and how to close the gap.

## Method

Pre-registered before the production run in [`EXPERIMENT.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/EXPERIMENT.md).

- **One flag:** `onboarding_method`, multivariate, control `prompt`, variation `skill` (with a key so exposures are recorded), 100% of trials enrolled, 50/50. The identity is the trial ID and the exposure is recorded when the runner reads the flag, before the agent starts.
- **One trial:** one headless agent run on one small sample app (React, Node or Python, picked at random). The agent is OpenCode 1.19.6 with `MiniMaxAI/MiniMax-M3.1-Flash` on Nebius Token Factory, the same for both arms. Same tools, limits, task brief and sample-app pool. Only the handoff differs: the official prompt unedited, or the skill installed in the agent's skill folder ([`docs/fairness.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/docs/fairness.md)).
- **Primary metric:** `integration_verified`, sent only when a ground-truth grader passes checks C1 to C6: the app runs, an exposure is sent, the conversion is sent on click and not on load, exposure and conversion share one identity, the identity is stable across reload and differs for a new visitor, and the flag value drives the UI. The grader reads recorded network traffic from the agent's app behind an intercepting proxy ([`docs/grader.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/docs/grader.md)).
- **Guardrail metric:** `over_budget`.
- **Sample size and rule:** 220 trials fixed in advance. Ship the winner only if the win probability is at least 95%, the credible interval excludes zero and the guardrail is not worse. The prompt arm meets the rule.
- **Checks on the checker:** a blind review of 24 passing diffs (12 per arm, arm hidden from the reviewer) found 24 real passes and 0 false passes ([`docs/blind-audit.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/docs/blind-audit.md)). All 18 graded failures were root-caused from their diffs ([`docs/failure-labels.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/docs/failure-labels.md)).

Scope, stated plainly: one agent and one model, small sample apps, and the grader judges wiring from network behaviour against a local Flagsmith emulator, so `integration_verified` means the code the agent wrote is wired correctly. It does not check the Flagsmith-side setup.

## Why the prompt arm leads, and what it suggests

All 10 React skill failures lost events in the browser: the SDK's `isomorphic` entry (9 trials) or `fetch: globalThis.fetch` (1 trial) was used, the SDK then calls an unbound `fetch`, and no event leaves the page while flags and UI still look right. The prompt sends the agent to the docs page, which shows `import flagsmith from '@flagsmith/flagsmith'`. All 108 prompt-arm trials read that page and none used the isomorphic entry. Four Node trials enabled local evaluation, which the grader's local emulator does not serve; they are counted as failures under the pre-registered rule and shown separately in a sensitivity table (skill 96/108 without them). The remaining skill failure added a 30 s cache that suppressed the second exposure.

This points at a general lesson for skills: keep one pointer to the living docs page and put the exact import path in every snippet. Skill v2 in the repo encodes these fixes ([`skill/flagsmith-ab-test-v2/`](https://github.com/vivekyarra/prompt-vs-skill/tree/main/skill/flagsmith-ab-test-v2)).

## Concrete suggestions for the official setup prompt and docs

Each item says how it was established. SDK versions: `flagsmith` 6.7.0 (Python), `@flagsmith/nodejs` 9.5.0, `@flagsmith/flagsmith` 12.6.0, plus live calls to a Flagsmith Cloud project. Details are in [`docs/flagsmith-sdk-notes.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/docs/flagsmith-sdk-notes.md).

**1. Python: `EventProcessorConfig(max_buffer_items=1)` can drop the exposure.**
The prompt's step 8 tells Python users to flush with `EventProcessorConfig(max_buffer_items=1)`. With `flagsmith` 6.7.0, when `get_experiment_flag(...)` is immediately followed by `track_event(...)`, the one-item buffer evicts the exposure ("Event buffer was full: dropped the 1 oldest events"). Over repeated runs of the same script the exposure was sent in 0 of 6 runs with `max_buffer_items=1` and in 6 of 6 runs with the default buffer plus an explicit `flush_events()`. Suggestion: recommend the default buffer and `flush_events()` (then `close()`) for short-lived Python scripts.

**2. Document `flush_events()` / `flushEvents()` next to `close()`.**
The SDKs buffer events and send them on a 10 s timer (or at 1000 events), and the Python client does not close itself at exit, so unflushed events are lost when a short script ends. `flush_events()` exists in Python 6.7.0 and `flushEvents()` exists in the Node and JS SDKs (verified from source, observed for Node). Tooling that checks traffic must wait at least the flush interval: our grader waits 13 s, and a shorter wait wrongly failed correct integrations in our pilot.

**3. Branch on the flag value, not the variant key.**
Live against Flagsmith Cloud with the Python SDK, a control-bucket identity returned `value='prompt'` with `variant='control'`, and a treatment-bucket identity returned `value='skill'` with `variant='skill'`. `.variant` is the bucket name and does not match the flag's configured values; `.value` carries them. Suggestion: say in the prompt and docs that UI logic should branch on the flag value. The exposure event's `value` field is the variant key, which is a different thing.

**4. Give the experiment and metric request bodies in the API reference.**
The exact JSON bodies for creating a metric (`POST .../experiment-metrics/`), an experiment (`POST .../experiments/`, including `experiment_rollout` and `multivariate_feature_state_values`) and the `start/` call are given in the setup prompt. In our reading the stand-alone experimentation pages do not give them in one place, so an API-reference entry would let agents and people avoid probing validation errors. We ran all of these live: metric `occurrence`/`up`, experiment created, `start/` returned 200 with `status: running`. Please check the "not elsewhere" part against the current docs.

**5. A detached `fetch` silently drops all events in the JS SDK.**
Beyond the 10 React failures above, an earlier Development trial showed that passing `fetch: globalThis.fetch` in the JS SDK options delivers no event and raises no error; removing that line made the app pass every check. Suggestion: a one-line note in the JS SDK docs about unbound `fetch` and the `isomorphic` entry in browsers, or an SDK warning when event delivery throws.

**6. Exposure only fires when the experiment is running and the identity is enrolled.**
`getExperimentFlag` / `get_experiment_flag` emit `$flag_exposure` only if the flag exists and is enabled, the identity is enrolled in a running experiment, and a variant key is present. Otherwise the call behaves as a plain flag read and nothing is sent, with no warning. The JS SDK additionally needs the flags to have come from the server. Suggestion: say in the verify step to start the experiment before checking for an exposure, and consider a debug log line when an experiment flag read does not emit.

## Offer

We would be glad to contribute a skill to the official skills repository, with whatever changes the maintainers want. The v1 skill and the official prompt are both in the repo, and v2 carries the fixes above.

## Links

- Repo: https://github.com/vivekyarra/prompt-vs-skill
- Pre-registration: https://github.com/vivekyarra/prompt-vs-skill/blob/main/EXPERIMENT.md
- Results: https://github.com/vivekyarra/prompt-vs-skill/blob/main/RESULTS.md
