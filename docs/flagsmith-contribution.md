<!--
DRAFT, ready to post once filled. A human reviews and posts this.
Before posting: replace every {{TBD ...}} from RESULTS.md and the Flagsmith dashboard, delete this comment,
and delete or keep the conditional "Offer" section according to the pre-registered decision rule.
Do not post with any {{TBD}} left in. No result number may be written from memory.
-->

**Title:** Experiment: Flagsmith's official coding-agent setup prompt vs an Agent Skill, plus concrete fixes for the setup prompt ({{TBD one-line result from RESULTS.md}})

## Question

Does an Agent Skill get a coding agent to a correctly wired Flagsmith A/B test more often than Flagsmith's official setup prompt ([Set up with a coding agent](https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent))?

We ran the comparison as a real Flagsmith experiment and used the experiment to answer it. The experiment is the test; this issue reports the outcome and, separately, a few specific things we found in the setup material while building it.

## Method

Pre-registered before the production run in [`EXPERIMENT.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/EXPERIMENT.md). The decision rule, metrics and sample size below were fixed up front.

- **One flag:** `onboarding_method`, multivariate, control `prompt`, variation `skill` (with a key so exposures are recorded). 100% of trials enrolled, 50/50. Identity is the trial ID. Exposure is recorded when the runner reads the flag, before the agent starts.
- **One trial:** one headless agent run on one small sample app (React, Node or Python, picked at random per trial). The agent is OpenCode 1.19.6 with `MiniMaxAI/MiniMax-M3.1-Flash` on Nebius Token Factory, the same for both arms. Same tools, turn and token limits, task brief and sample-app pool; only the handoff differs (the official prompt unedited, or the skill installed in the agent's skill folder). See [`docs/fairness.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/docs/fairness.md).
- **Primary metric:** `integration_verified`, sent only when a ground-truth grader passes checks C1-C6 (app runs; exposure sent; conversion on click, not on load; same identity on exposure and conversion; identity stable across reload and different for a new visitor; the flag value drives the UI). The grader reads recorded network traffic from the agent's app behind an intercepting proxy.
- **Guardrail metric:** `over_budget` (the agent hit the turn or token limit; lower is better).
- **Sample size:** N = 220 trials total (about 110 per variant), fixed in advance. This is below the original 150-200 per variant target because of a budget cap; that is a stated deviation, not a change to the pre-registration.
- **Decision rule:** ship the winner only if Flagsmith reports a win probability of at least 95% AND the credible interval on the difference excludes zero AND the guardrail is not significantly worse for it. Otherwise the result is reported as inconclusive. Stopping rule: stop at N = 220 or at the deadline, never because the result looks good. If Flagsmith's results `inference` is null at the end, the rule is applied with our own Beta-Binomial analysis, labelled as ours.

### What this measures, and what it does not

- The grader answers all `*.flagsmith.com` requests with a mock and always reports the trial's flag as enrolled in a running experiment. `integration_verified` therefore means "the code the agent wrote is wired correctly" (experiment-flag read, exposure, conversion on click, same stable identity, UI driven by the flag). It does **not** verify the Flagsmith-side setup (flag, keyed variation, metric, experiment) that the agent may or may not have created.
- Check C6 compares the rendered text with the flag **value**. An app that branches on the variation key cannot be verified and is scored as failing C6.
- One agent, one open-weight model, small sample apps. A ceiling effect is expected (both arms near 90% or higher), in which case a true difference under roughly 10 percentage points will most likely be reported as inconclusive.

## Results

Filled from `RESULTS.md` and the Flagsmith experiment dashboard only after the run has finished.

| Field | Value |
|---|---|
| Trials completed / runner errors | {{TBD from RESULTS.md}} |
| Exposures (prompt / skill) and sample-ratio check | {{TBD from RESULTS.md}} |
| `integration_verified` rate (prompt / skill) | {{TBD from RESULTS.md}} |
| Credible interval on the difference | {{TBD from Flagsmith dashboard}} |
| Win probability | {{TBD from Flagsmith dashboard}} |
| Guardrail `over_budget` (prompt / skill) | {{TBD from RESULTS.md}} |
| Decision under the pre-registered rule | {{TBD: ship / inconclusive}} |
| Most common failing checks per variant | {{TBD from RESULTS.md, failure breakdown}} |
| Flagsmith dashboard read at (UTC) | {{TBD}} |

## Concrete suggestions for the official setup prompt/skill

These come from facts we verified while building the experiment (SDK source read and spike scripts run against `flagsmith` 6.7.0 for Python, `@flagsmith/nodejs` 9.5.0, `@flagsmith/flagsmith` 12.6.0, plus live calls to a Flagsmith Cloud project). Each item says how it was established. Source files are in the repo: [`docs/verified-facts.md`](https://github.com/vivekyarra/prompt-vs-skill/blob/main/docs/verified-facts.md) and [`spike/`](https://github.com/vivekyarra/prompt-vs-skill/tree/main/spike). They are independent of who won the experiment.

**1. Python: `EventProcessorConfig(max_buffer_items=1)` can drop the exposure.**
The prompt's step 8 tells Python users to flush with `EventProcessorConfig(max_buffer_items=1)`. With `flagsmith` 6.7.0, when `get_experiment_flag(...)` is immediately followed by `track_event(...)`, the one-item buffer evicts the exposure ("Event buffer was full: dropped the 1 oldest events"). Verified by running the same script repeatedly: the exposure was sent in 0 of 6 runs with `max_buffer_items=1`, and in 6 of 6 runs with the default buffer plus an explicit `flush_events()`. Suggestion: recommend the default buffer and `flush_events()` (then `close()`) for short-lived Python scripts. Source: `spike/py_buffer_race.sh`; `docs/verified-facts.md` section 1.3.

**2. Document `flush_events()` / `flushEvents()` next to `close()`.**
The SDKs buffer events and send them on a 10 s timer (or at 1000 events), and the Python client does not close itself at exit, so unflushed events are lost when a short script ends. In the SDK source, `flush_events()` exists in Python 6.7.0 and `flushEvents()` exists in the Node and JS SDKs; the prompt lists `flushEvents()` for JavaScript and Flutter, `close()` for Node and Java, and the `max_buffer_items=1` workaround (see 1) for Python. Verified from source (Python, Node, JS) and observed for Node. Not tested by us: a browser page that is closed or navigated away before the timer fires; we infer it loses buffered events from the same timer, so an explicit flush after the exposure and after the conversion is the safe advice. A side effect we hit ourselves: tooling that checks traffic must wait at least the flush interval (we wait 13 s) or it will wrongly report that no event was sent. Source: `docs/verified-facts.md` section 1.3; `docs/pilot-regrade.md` (seven pilot integrations that were wrongly failed by a too-short wait).

**3. Branch on the flag value, not the variant key.**
Live against Flagsmith Cloud with the Python SDK, a control-bucket identity returned `value='prompt'` with `variant='control'`, and a treatment-bucket identity returned `value='skill'` with `variant='skill'`. So `.variant` is the bucket name (`control` for the control bucket) and does not match the flag's configured values; `.value` carries them. Suggestion: state in the prompt and docs that UI logic should branch on the flag value. Note that the exposure event's `value` field is the variant key, which is a different thing from the value you branch on. Source: `docs/verified-facts.md` section 10 ("SDK behaviour").

**4. Document the experiment and metric request bodies outside the prompt.**
The exact JSON bodies for creating a metric (`POST .../experiment-metrics/`) and an experiment (`POST .../experiments/`, including `experiment_rollout` and `multivariate_feature_state_values`), and the `start/` call, are given in the setup prompt. In our reading the stand-alone experimentation how-to pages do not give them in one place; if that is right, an API-reference entry would let agents (and people) avoid probing validation errors. We ran all of these live and they succeeded (metric `occurrence`/`up`, experiment created, `start/` returned 200 with `status: running`). The API values for other aggregations and directions are unverified by us. Please treat the "undocumented" part as our reading and check it against the current docs. Source: `prompt/OFFICIAL_PROMPT.md`; `docs/verified-facts.md` sections 5 and 10.

**5. Pitfall observed once: a detached `fetch` silently drops all events (JS SDK).**
In one pilot trial an agent passed `fetch: globalThis.fetch` in the JS SDK options and no event was ever delivered, with no error. Removing that single line made the app pass every check. This is one observation (React, skill arm, CI run 45907896688), not a measured rate. We believe the cause is a detached `fetch` losing its receiver; we did not test that mechanism separately. Suggestion: a one-line note in the JS SDK docs not to pass an unbound `fetch`, or an SDK guard or console warning when event delivery throws. Source: `EXPERIMENT.md` freeze log.

**6. Exposure only fires when the experiment is running and the identity is enrolled.**
`getExperimentFlag` / `get_experiment_flag` emit the `$flag_exposure` event only if the flag exists and is enabled, the identity is enrolled in a running experiment, and a variant key is present; otherwise the call behaves as a plain flag read and nothing is sent, with no warning. The JS SDK additionally needs the flags to have come from the server, not from cache or defaults. Verified from the source of all three SDKs. Suggestion: say so explicitly in the "verify" step (start the experiment before checking for an exposure) and consider a debug log line when an experiment flag read does not emit. Source: `docs/verified-facts.md` section 1.3.

## Offer

Conditional on the result: {{TBD from RESULTS.md: only if the skill won under the pre-registered decision rule, keep the sentence below; otherwise delete this section}}

If the skill won under the rule above, we would be glad to contribute it (`skill/flagsmith-ab-test/`, written from Flagsmith's published documentation, with no reference to the study) to the official skills repository, with whatever changes the maintainers want. If the result was inconclusive or the prompt won, we are not proposing the skill; the suggestions above stand on their own.

## Links

- Repo: https://github.com/vivekyarra/prompt-vs-skill
- Pre-registration: https://github.com/vivekyarra/prompt-vs-skill/blob/main/EXPERIMENT.md
- Results: {{TBD link to RESULTS.md in the repo}}
- Flagsmith experiment dashboard: {{TBD link}}
