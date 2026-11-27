# Flagsmith SDK and API notes

What the three SDKs, the Flagsmith CLI and the management API actually do, as read from official docs and SDK source and observed by running the code. The grader, the runner and the skills depend on these facts. `docs:` means the official Flagsmith docs, `src:` the installed package source, `observed` means seen by running the code.

Versions: `@flagsmith/flagsmith` 12.6.0, `@flagsmith/nodejs` 9.5.0, `flagsmith` (Python) 6.7.0, `@flagsmith/cli` 2.0.0, Node 22.23.5, mitmproxy 12.3.1, Playwright 1.63.0 (Chromium 158).

## 1. Wire format (the grader depends on this)

### 1.1 Hosts and paths

| Fact | Value | Source |
|---|---|---|
| Default API host (flags/identities), all 3 SDKs | `https://edge.api.flagsmith.com/api/v1/` | src: python `flagsmith.py` `DEFAULT_API_URL`; observed in mitm capture (host `edge.api.flagsmith.com`, path `/api/v1/...`) for node, python, js |
| Default events host, all 3 SDKs | `https://events.api.flagsmith.com/` ; SDK appends `v1/events` -> `POST https://events.api.flagsmith.com/v1/events` | src: python `analytics.py` `DEFAULT_EVENT_API_URL`, `f"{url}v1/events"`; node `events.js` `EVENTS_ENDPOINT='v1/events'`; js bundle; observed  |
| Identity flag evaluation, Python & Node | `POST {api}/identities/` JSON `{"identifier":"example-1","traits":[]}` | src: python `utils/identities.py`; observed |
| Identity flag evaluation, JS | with no traits: `GET {api}/identities/?identifier=example-1` (after an initial unidentified `GET {api}/flags/`); with traits: `POST {api}/identities/` | src: `flagsmith-core.ts` getFlags; observed (JS in node and in Chromium) |
| Flag analytics (not events, disabled by default) | `POST {api}/analytics/flags/` body `{"<flag>": count}` | src: python `analytics.py`; only when `enable_analytics`/`enableAnalytics` is on; NOT part of experimentation |
| Self-hosted events URL (Flagsmith DB mode) | set events URL to `<flagsmith api>/api/`; SDK appends `v1/events` -> `<host>/api/v1/events` | docs: experimentation/self-hosting |
| Self-hosted events URL (own warehouse) | event ingestion service URL, e.g. `https://events.flagsmith.example.com/` | docs: experimentation/self-hosting |

### 1.2 Events request (exposure AND conversion use the same endpoint, batched)

`POST <events-url>v1/events`

Headers (all three SDKs): `Content-Type: application/json; charset=utf-8`, `X-Environment-Key: <env key>`,
`Flagsmith-SDK-User-Agent: flagsmith-{js-sdk|nodejs-sdk|python-sdk}/<version>` (the events pipeline reads SDK language/version from this one;
Python's plain `User-Agent` is `python-requests/x`, so graders must use `Flagsmith-SDK-User-Agent` to identify the SDK). Identity is NOT in a header. **Header names must be matched case-insensitively**: Chromium over mitmproxy (HTTP/2) delivers them lower-case (`x-environment-key`, `flagsmith-sdk-user-agent`; observed), Node/Python deliver them in the cases shown.

Body (observed in direct, proxy and browser captures):

```json
{"events": [{"event": "$flag_exposure", "feature_name": "example_flag", "identifier": "example-1", "value": "treatment_key", "traits": null, "metadata": {"experiment_id": 7, "sdk_version": "9.5.0"}, "timestamp": 1795708714106}, {"event": "spike_event", "feature_name": null, "identifier": "example-1", "value": "1.5", "traits": null, "metadata": {"sdk_version": "9.5.0"}, "timestamp": 1795708714106}]}
```
(Body of a Node SDK request; the other SDKs differ only in `sdk_version`; Python's exposure carries the same `experiment_id` metadata.)

| Field | Meaning (verified) |
|---|---|
| `events[]` | Batch. Exposure and conversion events are interleaved in one array; one POST can hold many identities |
| `event` | Exposure = literal `"$flag_exposure"` (constant `FLAG_EXPOSURE_EVENT`); conversion = the name passed to `trackEvent`/`track_event` (case-sensitive; names starting with `$` are rejected by the SDK with an error) |
| `feature_name` | Flag name for exposures; `null` for conversions |
| `identifier` | The identity string (`example-1`). Exposure and conversion must carry the same identifier to join |
| `value` | Always a string or null: exposure = the **variant key** served (`flag.variant`); conversion = `str(value)` (`1.5` -> `"1.5"`) or null |
| `traits` | dict or `null` |
| `metadata` | `sdk_version` always; exposures from `get_experiment_flag`/`getExperimentFlag` add `experiment_id` (int). Python's metadata for a manual `track_event` has only `sdk_version` |
| `timestamp` | ms since epoch (docs: events older than 10 days or >24 h in the future are rejected; batch >2 MiB rejected whole) |

Sources: src python `analytics.py` `_buffer_event`/`_deliver`; node `build/esm/sdk/events.js`; js bundle `index.mjs` (EventProcessor) + `event-processor.d.ts` (`IEvent`); observed in all three captures. Response handling: Python treats any status <400 as delivered, Node and JS only 2xx (src python `_outcome_of`; node `events.js`; js bundle `s>=200&&s<300`), so the emulator must answer events with **200**. 401/403 = key refused (SDK stops tracking and drops its buffer); 408/429/500/502/503/504 retried, up to 3 attempts per flush (src python `EVENTS_MAX_ATTEMPTS`, node `MAX_ATTEMPTS=3`; JS retries with exponential backoff, attempt count not read).

### 1.3 Batching, flushing, dedup (behaviour that decides whether a request ever appears)

| Fact | Value | Source |
|---|---|---|
| Default flush | every 10 s, or when buffer reaches 1000 events | src python `EventProcessorConfig` (`flush_interval_seconds=10`, `max_buffer_items=1000`); js `flushInterval=1e4, maxBuffer=1e3` |
| Events are batched | Yes; exposure + conversion tracked close together arrive in ONE POST | observed (all three) |
| Exposure only emitted when | flag exists AND enabled AND `experiment.in_experiment` true AND a `variant` key is present. Otherwise the SDK silently emits nothing. So against an emulator or a real server that does not return `metadata.experiment.in_experiment=true` + `variant`, NO exposure is ever sent | src python `get_experiment_flag`, node `getExperimentFlag`, js `getExperimentFlag` |
| Identity response fields the SDK needs for an exposure | `flags[].enabled`, `flags[].feature_state_value`, `flags[].feature.{id,name}`, `flags[].variant`, `flags[].metadata.experiment.{id,name,in_experiment}` | src python `models.py` `Flag.from_api_flag`, `ExperimentMetadata`; js `getFlags` |
| JS only emits an exposure if flags came from the server | `loadingState.source === SERVER` (not cache/defaults) | src js `getExperimentFlag` |
| Exposure dedup | per buffer window, identical (feature, identifier, value) exposures collapse to one in the buffer | src python `_buffered_exposure_keys`; docs: also deduplicated per identity server-side |
| Python flush in short scripts | **`flush_events()` and `close(timeout_seconds=5)` exist in 6.7.0** (docs mention only `max_buffer_items=1`). Client does not close itself at exit; unflushed events are lost | src python `flagsmith.py` |
| **PITFALL: official prompt's Python advice drops exposures** | With `EventProcessorConfig(max_buffer_items=1)`, `get_experiment_flag(...)` immediately followed by `track_event(...)` evicts the exposure ("Event buffer was full: dropped the 1 oldest events"). 0/6 runs sent the exposure; with the default buffer + `flush_events()` 6/6 sent it | observed (6 repeated runs of a short Python script) |
| Node flush | `await flagsmith.flushEvents()` exists (docs only show `await close()`); `close(timeoutMs?)` also flushes | src node `index.js`; observed |
| Node `trackEvent` needs identifier | `trackEvent(name, {identifier, value})`; without `identifier` the event is sent with `identifier: null` (no join) | src node `index.js` |
| JS `trackEvent` identity | defaults to the identity set by `identify()` | src js `flagsmith-core.ts` |
| JS flush | `await flagsmith.flushEvents()`; `stop()`/`close()` also flush | src js |

### 1.4 What the grader should assert (derived)

An app is "instrumented" for experiment `onboarding_method` with metric event `E` iff the capture contains, for the same `identifier`:
(a) an event with `event == "$flag_exposure"` and `feature_name == "onboarding_method"` and a non-null `value` (variant key), and
(b) a later-or-same-batch event with `event == "E"` exactly (case-sensitive), from a request whose `X-Environment-Key` header (name matched case-insensitively) is the expected key.
The grader's emulated identities response MUST include `metadata.experiment.in_experiment: true` and a `variant` key for the target flag, otherwise correct code looks broken.

## 2. SDK API (method names, options)

| Fact | JS (`@flagsmith/flagsmith` 12.6.0) | Node (`@flagsmith/nodejs` 9.5.0) | Python (`flagsmith` 6.7.0) | Source |
|---|---|---|---|---|
| Install | `npm i @flagsmith/flagsmith@^12.4.0` | `npm i @flagsmith/nodejs@^9.1.0` (old pkg `flagsmith-nodejs` cannot) | `pip install "flagsmith>=6.3.0"` | docs: experimentation/run-an-experiment |
| Enable events | `init({environmentID, enableEvents:true})` | `new Flagsmith({environmentKey, enableEvents:true})` | `Flagsmith(environment_key=..., enable_events=True)` | docs + src |
| Custom API URL | `api: '.../api/v1/'` | `apiUrl: '.../api/v1/'` | `api_url='.../api/v1/'` | docs + src |
| Custom events URL | `eventProcessorConfig:{eventsApiUrl}` (requires `enableEvents`, else init throws) | `eventProcessorConfig:{eventsApiUrl}` | `event_processor_config=EventProcessorConfig(events_api_url=...)` (requires `enable_events`, else ValueError) | docs + src |
| Identify | `await flagsmith.identify('id')` | n/a, identifier passed per call | n/a | docs |
| Experiment flag (records exposure) | `flagsmith.getExperimentFlag('flag')` (sync, after identify) | `await getExperimentFlag('flag','id')` | `get_experiment_flag('flag', identifier='id')` | docs + src + observed |
| Evaluate without exposure, then record manually | `getAllFlags()` + `trackExposureEvent(name,{value})` | `getIdentityFlags(id)` + `trackExposureEvent(name,{identifier,value})` | `get_identity_flags(id).get_flag(n)` + `track_exposure_event(name, identifier=, value=)` | docs |
| Conversion | `trackEvent('e',{value})` | `trackEvent('e',{identifier,value})` | `track_event('e', identifier=, value=)` | docs + src |
| Flush | `await flushEvents()` | `await flushEvents()` / `await close()` | `flush_events()` / `close()` (docs only: `max_buffer_items=1`, see pitfall) | src |
| Events disabled behaviour | JS no-ops silently; Node/Python raise (`enableEvents must be true`/`ValueError`) | raise | raise | src |
| Uses global fetch (Node) | `@flagsmith/flagsmith/isomorphic` uses global fetch; default entry (`.`) uses `unfetch`/XHR (browser only) | global `fetch` (undici) | `requests` | src; observed |
| Browser bundle | `index.js` is UMD, sets `window.flagsmith` | n/a | n/a | observed  |


## 3. Interception: what is proven

| Stack | App pointed at the local emulator by URL options | HTTPS proxy for the default hosts (used for trials) |
|---|---|---|
| Node SDK | Identities and events captured | Works with `NODE_USE_ENV_PROXY=1` + `HTTPS_PROXY` + `https_proxy` + `NODE_EXTRA_CA_CERTS=<mitm ca>` on Node 22. Without `NODE_USE_ENV_PROXY=1`, `HTTPS_PROXY` is ignored and 0 requests are captured |
| JS SDK in Node (isomorphic) | Works | Same environment as Node |
| Python SDK | Works (default buffer + `flush_events()`) | Works with `HTTPS_PROXY` + `https_proxy` + `REQUESTS_CA_BUNDLE` + `SSL_CERT_FILE` = mitm CA |
| JS SDK in Chromium (Playwright) | A page served from `http://127.0.0.1:<port>` can call the emulator on another loopback port with no special flag | Works with `chromium.launch(proxy=...)` + `new_context(ignore_https_errors=True)` |

Gotchas:

- **Lowercase proxy variables win.** Node/undici and Python `requests` read lowercase `https_proxy` first, so the grader sets both `HTTPS_PROXY` and `https_proxy` and clears `NO_PROXY`.
- The mitmproxy addon (`grader/mitm_addon.py`) answers `*.flagsmith.com` itself, with no upstream and no credentials. Forwarding mode to the real hosts is not used.
- `playwright==1.63.0` matches Chromium build 1243. mitmproxy needs its CA only for non-browser clients.
- The events URL is a separate option from the API URL in all three SDKs. Pointing only the API URL at an emulator would miss exposures and conversions, which is why the grader intercepts the default hosts and does not depend on the agent's configuration.

## 4. Agent Skills

| Fact | Value |
|---|---|
| Claude Code project skill location | `<cwd>/.claude/skills/<name>/SKILL.md` (frontmatter `name`, `description`), discovered natively in headless mode (observed) |
| Agent Skills spec | `SKILL.md` with YAML frontmatter: `name` (64 chars max, lowercase, digits, hyphens), `description` (1024 chars max), optional `license`, `compatibility`, `metadata`, `allowed-tools`; optional `scripts/`, `references/`, `assets/` (https://agentskills.io/specification) |

## 5. Flagsmith CLI v2 and experiment lifecycle

CLI install: `npm install -g @flagsmith/cli` (2.0.0) installs a Go binary (`flagsmith version v2.0.0`); `curl -fsSL https://get.flagsmith.com | sh`
(script reachable, downloads from GitHub Releases, default `v2.0.0`; **not executed**, `npm` path used instead) or `brew install Flagsmith/tap/flagsmith`. Source: docs: integrating-with-flagsmith/CLI; observed `--help` output below.

| Fact | Value | Source |
|---|---|---|
| Management API credential env (headless) | `FLAGSMITH_API_KEY` = a **Master API key** in `{prefix}.{secret}` form (CLI rejects other shapes: "not a Master API key (expected {prefix}.{secret})"); alternative `FLAGSMITH_ACCESS_TOKEN` (OAuth). No OS keychain in a container (`dbus-launch` missing) so `flagsmith login` is not usable headless | docs CLI page; observed error messages |
| SDK-side credential for `flagsmith eval` | `FLAGSMITH_ENVIRONMENT_KEY` | docs |
| Self-hosted credential var | `FLAGSMITH_API_KEY_<host-munged>` e.g. `FLAGSMITH_API_KEY_flagsmith_corp__internal_io_8000` | docs |
| Other env | `FLAGSMITH_API_URL` (flag `--api-url`, default `https://api.flagsmith.com`), `FLAGSMITH_PROJECT`, `FLAGSMITH_ENVIRONMENT` (client-side SDK key), `FLAGSMITH_ORGANISATION`, `FLAGSMITH_CONFIG_PATH`, `FLAGSMITH_NO_INPUT`, `FLAGSMITH_JSON_OUTPUT`, `FLAGSMITH_SDK_API_URL` | observed `--help` |
| Bind project | `flagsmith init --project <p> --environment <env key>` writes `flagsmith.json`; `flagsmith project list`, `flagsmith environment list --project <p>` | docs: set-up-with-a-coding-agent; observed `--help` (`init` has `--create-project`, `--create-environment`) |
| Create multivariate flag | `flagsmith feature create <flag> --value control --enabled` then `flagsmith feature variant add <flag> --value <v> --key <key> --weight 0`; check `flagsmith feature get <flag> --json`. `--variants` on `create` cannot set keys; every variation needs a `--key` or no exposures are recorded; `control` is reserved for the flag's own value | docs: set-up-with-a-coding-agent; flags observed in `--help` |
| Delete flag | `flagsmith feature delete <flag>` (use `--yes` for non-interactive) | observed `--help` |
| Create metric | `flagsmith api api/v1/environments/<env key>/experiment-metrics/ -X POST --input -` with `{"name":"<n>","aggregation":"occurrence","direction":"up","definition":{"version":1,"event":"<event>"}}` (the only payload shown in the docs uses `"aggregation":"occurrence"`, `"direction":"up"`; Occurrence/Count/Sum/Mean are UI names, the API values for count/sum/mean and other directions were not tried) | docs: set-up-with-a-coding-agent, create-metrics. No dedicated CLI subcommand (`flagsmith --help` has none) |
| Create experiment | `flagsmith api api/v1/environments/<env key>/experiments/ -X POST --input -` (i.e. `POST api/v1/environments/<env key>/experiments/`) `{"feature":<flag id>,"name":..,"hypothesis":..,"metrics":[{"metric":<metric id>,"expected_direction":"increase"}],"experiment_rollout":{"enabled":true,"rollout_percentage":100,"feature_state_value":{"type":"string","value":"control"},"multivariate_feature_state_values":[{"multivariate_feature_option":<variation id>,"percentage_allocation":50}]}}` | docs: set-up-with-a-coding-agent |
| **Start experiment** | `flagsmith api api/v1/environments/<env key>/experiments/<id>/start/ -X POST`, then check status is `running`. Starting is documented and works through the API and CLI (`flagsmith api`); the call returned 200 with `status: running` (section 8). Only the Flagsmith MCP server cannot start experiments | docs: set-up-with-a-coding-agent |
| Results | `POST .../experiments/<id>/results/refresh/` (allowed once per 5 min), `GET .../experiments/<id>/results/` | docs |
| Warehouse check | `GET api/v1/environments/<env key>/warehouse-connections/` must be non-empty; the events service rejects events for environments without one (a warehouse connection is a prerequisite; in practice one is auto-provisioned, see section 8) | docs |
| Running experiment | flag and variations locked; rollout % editable; an ended experiment cannot be restarted | docs: create-an-experiment |
| `flagsmith api` | `flagsmith api <path> [-X METHOD] [-F k=v] [-f k=v] [--input file\|-] [--sdk] [-i]`; typed `-F` builds JSON, POST implied | observed `--help` |
| Global flags | `--json`, `--jq <expr>`, `--no-input`, `--yes`, `-p/--project`, `-e/--environment`, `--organisation` | observed `--help` |

## 6. Official prompt

Stored verbatim in `prompt/OFFICIAL_PROMPT.md` (SHA-256 `35ecba5b98c502c6aa94dccfc65ff6a9028a8672e01d02d2b07c8d1e7df7001d`, retrieved 2026-11-26 from https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent). Verify with `python prompt/verify_official_prompt.py`.

## 7. Rate limits and parallelism

| Fact | Value | Source |
|---|---|---|
| SDK endpoints (flags, identities, events) | "not rate limited, by design"; only monthly plan limits apply (Free plan: blocked when over plan limit after a warning email) | docs: administration-and-security/governance-and-compliance/system-limits |
| Management API (everything the CLI/`flagsmith api` calls) | default **500 requests per minute** (self-hosted: `USER_THROTTLE_RATE`). It is a per-user throttle, so all trials sharing one Master API key share this budget (the per-user scope is my inference from the variable name, not stated outright) | same page |
| Results refresh | once every 5 minutes per experiment | docs: set-up-with-a-coding-agent |
| Event acceptance window | timestamps within -10 days / +24 h; batch <= 2 MiB | docs: run-an-experiment |
| System limits | 1000 features/project, 500 segments/project, 2000 segment overrides/env | system-limits page |
| Recommendation | `max-parallel: 5` for the trial matrix (a trial agent plausibly makes tens of management calls; 5 concurrent stays far below 500/min); lower to 3 if any HTTP 429 appears in trial logs. Free-plan monthly SDK/event volume is a separate cap to check at the pilot (H6). Clean up sandbox flags after each trial (1000 features/project cap) | derived |

## 8. Live Flagsmith setup (run through `.github/workflows/ops.yml`, 2026-11-26)

Scripts: `ops/fslib.py`, `ops/setup_experiment.py`. 
**Accounts.** `FS_SANDBOX_ADMIN_KEY` is a Master key of org "Handoff Sandbox" (42328), project `handoff-sandbox` 56668 (Development env 121208, Production 121209). `FS_EXPERIMENT_ADMIN_KEY` is a Master key of org "Yarra's Org" (42327), which holds only `handoff-experiment` 56666 (Development 121204, Production 121205). Auth: `Authorization: Api-Key <key>` on `https://api.flagsmith.com/api/v1/`. The `FS_EXPERIMENT_SERVER_KEY` values (`ser.` keys, one per GitHub environment) are SDK keys, not management credentials; the management API addresses environments by their client key (`api_key`). Before the experiment admin key existed, the sandbox admin key got 404 on `projects/56666/` and 403 on all its environments.

**Warehouse.** `GET environments/<env key>/warehouse-connections/` -> 200, a list with one auto-provisioned connection per environment: `{"id": 13187|13188, "warehouse_type": "flagsmith", "status": "created", "status_detail": null, "name": "Flagsmith", "config": null, "total_events_received": 0, ...}` (Development 13187, Production 13188). It accepted events (below), so no paid warehouse was needed.

**Calls (env = `environments/<env client key>`):**

| Call | Body | Response |
|---|---|---|
| `POST projects/56666/features/` | `{"name":"onboarding_method","type":"MULTIVARIATE","initial_value":"prompt","default_enabled":true}` | 201, flag id 306199 (project-level: one flag serves both environments) |
| `POST projects/56666/features/306199/mv-options/` | `{"type":"unicode","string_value":"skill","key":"skill","default_percentage_allocation":0,"feature":306199}` | 201, option id 37439, `key` echoed as `skill` |
| `OPTIONS <env>/experiment-metrics/`, `OPTIONS <env>/experiments/` | | 200, DRF schema. Metric: aggregation count/sum/mean/occurrence; direction up/down/informational. Experiment metric `expected_direction`: increase/decrease/not_increase/not_decrease. No primary/secondary field exists: the metrics list has only `{metric, expected_direction}` |
| `POST <env>/experiment-metrics/` | `{"name":..,"aggregation":"occurrence","direction":"up"\|"down","definition":{"version":1,"event":<name>}}` | 201 `{"id","name","description","aggregation","direction","definition","experiments","created_at","updated_at"}`. Metrics are per environment |
| `POST <env>/experiments/` | exactly the official-prompt body (step 6) with two metrics (`integration_verified` increase, `over_budget` decrease) and one `multivariate_feature_state_values` entry at 50 | 201 `{"id","feature","name","hypothesis","status":"created",...}`; GET detail shows `feature` expanded, `metrics[].{id,metric,metric_name,aggregation,direction,expected_direction}`, `experiment_rollout` (with `audience`), `started_at`, `ended_at` |
| `POST <env>/experiments/<id>/start/` | none | 200, full experiment, `status: "running"`, `started_at` set |
| `POST <env>/experiments/<id>/results/refresh/` | none | 202 `null` |
| `GET <env>/experiments/<id>/results/` | | 200 `{"results":{"as_of","last_error_at","refresh_requested_at","payload":{"metrics":[{"variants":{"control":{"n","sum","sum_squares"}},"inference":{},"metric_id","conversions_timeseries":{...}}],"srm_p_value":null,"exposures_timeseries":{"points":[{"bucket","new_identities":{"control":1}}],"granularity":"hour"}},"is_final":false}}` |

Notes: the primary metric is not distinguishable in the API (first metric listed is `integration_verified`; we did not check whether the dashboard treats list order as primary). Ids: see `EXPERIMENT.md`.

**SDK behaviour (python `flagsmith`, identity `setup-check-1` in the Development experiment, traits `stack`).** `get_experiment_flag('onboarding_method', ...)` -> `Flag(enabled=True, value='prompt', variant='control', experiment.in_experiment=True)`. Identity `setup-check-2` was bucketed to skill: `value='skill'`, `variant='skill'`, in_experiment True. So `.value` carries the handoff variant (`prompt`/`skill`); `.variant` is `control` for the control bucket. `track_event('integration_verified', identifier=..)` + `flush_events()` returned without raising. About 30 s later the warehouse connection showed `total_events_received=2, unique_events_count=2` (one exposure + one conversion), and after `results/refresh/` the results payload showed 1 exposed identity (control) and 1 `integration_verified` conversion (metric 744), `over_budget` n=1 sum=0. Production environment exposure was deliberately NOT exercised (it would pollute the real experiment); the same code path applies and it is a pre-trial step.

**Development data note.** Development pilot experiment data includes `setup-check-1` (exposure + conversion) and `setup-check-2` (and a few more `setup-check-*` identities, one exposure each, no conversions). Exclude identifiers starting `setup-check-` from analysis; none of these use trial-like identifiers.

**Runner assumptions.** Variant read from `.value` confirmed (runner unchanged except its docstring). `AdminApiCleaner`: auth style and `GET projects/{id}/features/?search=` list shape (`results[].{id,name}`) confirmed live (on the experiment project with the same API). Sandbox flag deletion ran in every production trial (`cleanup_status` in the trial record).

## 9. OpenCode as the agent

The experiment uses OpenCode 1.19.6 with an OpenAI-compatible endpoint (Nebius Token Factory, base URL `https://api.tokenfactory.nebius.com/v1/`, `Authorization: Bearer <key>`). Facts below were observed with the installed binary.

| Fact | Value |
|---|---|
| Headless | `opencode run [message..]`; with piped stdin and no TTY the message is read from stdin. Exit code 0 on completion, 1 on a provider error |
| Any OpenAI-compatible base URL | custom provider with `npm: "@ai-sdk/openai-compatible"`, `options.baseURL`, `options.apiKey: "{env:VAR}"` |
| Agent Skills | Native: project skills load from `.opencode/skills/<name>/SKILL.md`. The skill is listed in the system prompt and the model loads it with the `skill` tool |
| Install / version | `npm i -g opencode-ai@1.19.6`; `opencode --version` prints `1.19.6`. The CLI changes quickly (the published JSON schema now has a "V2" config with `providers`/`permissions`/`agents` and marks `provider`/`permission`/`agent` deprecated), so CI pins the version | observed; https://opencode.ai/config.json |
| Config keys that WORK on 1.19.6 | the legacy ones: `provider.<id>.{npm,name,options,models}`, `permission`, `model` (`"<provider>/<model>"`). The V2 keys shown in the docs were not exercised | observed |
| Config delivery | env `OPENCODE_CONFIG_CONTENT` (inline JSON). Nothing is written to the workspace. Other env names seen in the binary: `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DISABLE_AUTOUPDATE`, `OPENCODE_DISABLE_MODELS_FETCH`, `OPENCODE_DISABLE_CLAUDE_CODE`, `OPENCODE_DISABLE_EXTERNAL_SKILLS` | observed (`strings` on the binary + runs) |
| Model reference with slashes | `-m nebius/Org/Name-1` is sent to the API as `model: "Org/Name-1"` (every Nebius id is `org/name`) | observed |
| Permission / tool restriction | `permission: {bash, edit, read, glob, grep, webfetch, skill: "allow"}` and `list, websearch, task, todowrite, question, lsp, external_directory, doom_loop: "deny"` gives exactly the tools `bash, edit, glob, grep, read, skill, webfetch, write` (denied tools are not offered). That mirrors the Claude set (Bash Read Write Edit Glob Grep WebFetch Skill); `edit` covers write. The `skill` tool is offered in BOTH variants; only Variant B has a skill advertised in the system prompt | observed |
| Turn limit | `agent.build.steps: 3` (docs: "maximum number of agentic iterations before forcing text-only response") did **NOT** stop a model that always returned a tool call: 1,981 messages, tools still offered. So the runner does not rely on it: it counts `step_finish` events and kills the process (same code path as Claude) | observed; docs: https://opencode.ai/docs/agents/ |
| Extra model call | without `--title`, `opencode run` makes a separate title-generation request (not in the event stream, so its tokens would go uncounted). `--title <text>` removes it | observed |
| Plugins / workspace writes | with a `.opencode/` dir present, opencode installs `@opencode-ai/plugin` into `.opencode/` (node_modules, package.json, lockfile; its own ignore file keeps them out of the diff) and needs npm network. `--pure` ("run without external plugins") avoids the install; skills still load with `--pure` | observed; `opencode run --help` |
| `--format json` events | one JSON object per line: `step_start`, `tool_use` (`part.tool`, `part.state.input/output`), `text` (`part.text`), `step_finish`, and `error` (`error.name`, `error.data.message`). No separate final "result" event | observed |
| Usage fields | `step_finish.part.tokens = {total, input, output, reasoning, cache:{write, read}}`, `part.cost`, `part.reason` (`tool-calls` or `stop`). With the scripted server reporting prompt 100 (30 cached) and completion 20 (5 reasoning): `input:70`, `output:15`, `reasoning:5`, `cache.read:30`. So `input` EXCLUDES cached tokens and `output` EXCLUDES reasoning; the runner adds them back (input_tokens = input+cache.read+cache.write, output_tokens = output+reasoning) | observed |
| Cost | `part.cost` was `0` (no model prices configured). The runner therefore computes cost from `HANDOFF_PRICE_IN_PER_M` / `HANDOFF_PRICE_OUT_PER_M` (all input tokens at the input price: an upper bound), else 0.0 | observed |
| Global state | config, data (sessions), cache live under XDG dirs; the runner points all four `XDG_*_HOME` at a per-trial temp dir and sets `OPENCODE_DISABLE_CLAUDE_CODE=1`, `OPENCODE_DISABLE_EXTERNAL_SKILLS=1` (skills from `.opencode/skills` still loaded with both set). `HOME` is still passed through, as for Claude | observed |
| Real binary through the runner | `run_trial` with the real `opencode` against the scripted server: Variant B loaded the skill, record has `agent: opencode`, `agent_version: 1.19.6`, token totals and price-based cost; a model that never stops was killed at turn N+1 with `limit_hit: turns`, exit -9, no surviving process | observed (scratch script, not committed) |
| The agent's shell | the `bash` tool inherits opencode's environment, so the agent can read `NEBIUS_API_KEY` (as the Claude agent can read `ANTHROPIC_API_KEY`). It never gets `FS_EXPERIMENT_SERVER_KEY` | by construction; unit-tested |

---

# Appendix: sample-app SDK verification

## Verified facts (sample apps / SDK methods)

Verified 2026-11-26 by installing the packages and reading their source (types, README, implementation).

## SDK experiment methods

| Stack | Package (verified version) | Methods (all exist as expected) |
|---|---|---|
| React / browser | `@flagsmith/flagsmith` 12.6.0 (npm) | `init({ enableEvents: true, eventProcessorConfig?: { eventsApiUrl } })`, `getExperimentFlag(name)` (sync, after `init`), `trackEvent(event, { identifier?, value?, traits?, metadata? })`, `flushEvents(): Promise<void>` |
| Node | `@flagsmith/nodejs` 9.5.0 (npm) | `new Flagsmith({ environmentKey, apiUrl, enableEvents: true, eventProcessorConfig?: { eventsApiUrl } })`, `await getExperimentFlag(name, identifier, traits?)`, `trackEvent(event, { identifier, ... })`, `await flushEvents()`, `close(timeoutMs?)` |
| Python | `flagsmith` 6.7.0 (PyPI) | `Flagsmith(environment_key, api_url, enable_events=True, event_processor_config=EventProcessorConfig(events_api_url=...))`, `get_experiment_flag(feature_name, identifier, traits=None)`, `track_event(event, identifier=None, ...)`, `flush_events()`, `close()` |

Discrepancies vs. the brief (none in method names; these are behavioural):

- The Python method is `enable_events=True` on the **constructor** (there is no separate `enable_events()` method); JS/Node likewise take `enableEvents: true` in config, not a method.
- Python flush is `flush_events()` (snake_case), not `flush_event`.
- The exposure endpoint is separate from the flags API: events go to `https://events.api.flagsmith.com/` (`POST <events url>/v1/events`), configured via `eventsApiUrl` / `events_api_url`, NOT via the flags API base URL. A grader that stubs only `FLAGSMITH_API_URL` still sees flag requests, but events need the events URL pointed at the emulator too. The reference apps expose this as optional `FLAGSMITH_EVENTS_URL` (server) / `VITE_FLAGSMITH_EVENTS_API` (React).
- `getExperimentFlag` / `get_experiment_flag` only emits the `$flag_exposure` event when the flag exists, is enabled, the identity is enrolled in a running experiment (`metadata.experiment.in_experiment == true` in the identities response) and the flag has a `variant`. Otherwise it behaves as a plain read and no exposure is sent. The exposure event `value` is the variant key (e.g. `"B"`), not the flag text value.
- Node and Python throw if `enableEvents` is not set when calling the experiment/track methods; `trackEvent`/`track_event` reject event names starting with `$`.
- Browser SDK `getExperimentFlag` returns `IFlagsmithFeature | null`; flag keys are lower-cased with spaces replaced by `_`. Node/Python SDKs require a server-side key only for local evaluation; remote evaluation (used here) accepts the key given.

Sources: `types.d.ts` and `src/flagsmith-core.ts` in the installed `@flagsmith/flagsmith` package; `sdk/index.ts`, `sdk/events.ts`, `sdk/types.ts` in the installed `@flagsmith/nodejs` package; `flagsmith/flagsmith.py` and `flagsmith/analytics.py` in the `flagsmith` wheel.

## Observed wire format (against a local emulator, real SDKs)

- Flags: browser `GET <api>/identities/?identifier=<id>`; Node/Python `POST <api>/identities/` with `{"identifier": "<id>", "traits": []}`.
- Events: `POST <events>/v1/events` with `{"events": [{"event": "$flag_exposure"|"join_clicked", "feature_name", "identifier", "value", "traits", "metadata", "timestamp"}]}`. Exposure and conversion carry the same `identifier` in all three reference apps.
- Default flush interval is a timer (10 s in Python); the reference apps call flush right after the exposure and after the click so events are sent within the grader's wait windows.