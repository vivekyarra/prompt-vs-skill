# Verified facts (Phase 0 spike, credential-free part)

Everything here was either read from official docs / SDK source, or observed by running the scripts in `spike/`.
Date of the spike: 2026-11-26. Nothing in this file was guessed. Anything that needs real Flagsmith credentials is marked
**UNVERIFIED (needs credentials)**; the Phase 0 acceptance item "one manual Flagsmith experiment created, started, with one
exposure and one event" is therefore **NOT done** (needs H1-H3).

Source shorthand: `docs:` = https://docs.flagsmith.com/ + path; `src:` = installed package source under `spike/*/node_modules` or the
pip package; `observed` = observed in spike (script named).

Versions installed and read: `@flagsmith/flagsmith` 12.6.0, `@flagsmith/nodejs` 9.5.0, `flagsmith` (python) 6.7.0, `@flagsmith/cli` 2.0.0
(binary `flagsmith version v2.0.0`), Node v22.23.5, Python 3.13, mitmproxy 12.3.1, Playwright 1.63.0 (Chromium HeadlessChrome/158), Claude Code 2.1.332.

## 1. Wire format (the grader depends on this)

### 1.1 Hosts and paths

| Fact | Value | Source |
|---|---|---|
| Default API host (flags/identities), all 3 SDKs | `https://edge.api.flagsmith.com/api/v1/` | src: python `flagsmith.py` `DEFAULT_API_URL`; observed in mitm capture (host `edge.api.flagsmith.com`, path `/api/v1/...`) for node, python, js |
| Default events host, all 3 SDKs | `https://events.api.flagsmith.com/` ; SDK appends `v1/events` -> `POST https://events.api.flagsmith.com/v1/events` | src: python `analytics.py` `DEFAULT_EVENT_API_URL`, `f"{url}v1/events"`; node `events.js` `EVENTS_ENDPOINT='v1/events'`; js bundle; observed (`spike/capture_mitm.jsonl`) |
| Identity flag evaluation, Python & Node | `POST {api}/identities/` JSON `{"identifier":"spike-1","traits":[]}` | src: python `utils/identities.py`; observed (`capture_direct.jsonl`) |
| Identity flag evaluation, JS | with no traits: `GET {api}/identities/?identifier=spike-1` (after an initial unidentified `GET {api}/flags/`); with traits: `POST {api}/identities/` | src: `flagsmith-core.ts` getFlags; observed (JS in node and in Chromium) |
| Flag analytics (not events, disabled by default) | `POST {api}/analytics/flags/` body `{"<flag>": count}` | src: python `analytics.py`; only when `enable_analytics`/`enableAnalytics` is on; NOT part of experimentation |
| Self-hosted events URL (Flagsmith DB mode) | set events URL to `<flagsmith api>/api/`; SDK appends `v1/events` -> `<host>/api/v1/events` | docs: experimentation/self-hosting |
| Self-hosted events URL (own warehouse) | event ingestion service URL, e.g. `https://events.flagsmith.example.com/` | docs: experimentation/self-hosting |

### 1.2 Events request (exposure AND conversion use the same endpoint, batched)

`POST <events-url>v1/events`

Headers (all three SDKs): `Content-Type: application/json; charset=utf-8`, `X-Environment-Key: <env key>`,
`Flagsmith-SDK-User-Agent: flagsmith-{js-sdk|nodejs-sdk|python-sdk}/<version>` (the events pipeline reads SDK language/version from this one;
Python's plain `User-Agent` is `python-requests/x`, so graders must use `Flagsmith-SDK-User-Agent` to identify the SDK). Identity is NOT in a header. **Header names must be matched case-insensitively**: Chromium over mitmproxy (HTTP/2) delivers them lower-case (`x-environment-key`, `flagsmith-sdk-user-agent`; observed in `spike/capture_mitm.jsonl`), Node/Python deliver them in the cases shown.

Body (observed, `spike/capture_direct.jsonl`, `capture_mitm.jsonl`, `capture_browser.jsonl`):

```json
{"events": [{"event": "$flag_exposure", "feature_name": "spike_flag", "identifier": "spike-1", "value": "treatment_key", "traits": null, "metadata": {"experiment_id": 7, "sdk_version": "9.5.0"}, "timestamp": 1795708714106}, {"event": "spike_event", "feature_name": null, "identifier": "spike-1", "value": "1.5", "traits": null, "metadata": {"sdk_version": "9.5.0"}, "timestamp": 1795708714106}]}
```
(Verbatim body of the Node SDK request in `spike/capture_direct.jsonl`; the other SDKs differ only in `sdk_version`; Python's exposure carries the same `experiment_id` metadata.)

| Field | Meaning (verified) |
|---|---|
| `events[]` | Batch. Exposure and conversion events are interleaved in one array; one POST can hold many identities |
| `event` | Exposure = literal `"$flag_exposure"` (constant `FLAG_EXPOSURE_EVENT`); conversion = the name passed to `trackEvent`/`track_event` (case-sensitive; names starting with `$` are rejected by the SDK with an error) |
| `feature_name` | Flag name for exposures; `null` for conversions |
| `identifier` | The identity string (`spike-1`). Exposure and conversion must carry the same identifier to join |
| `value` | Always a string or null: exposure = the **variant key** served (`flag.variant`); conversion = `str(value)` (`1.5` -> `"1.5"`) or null |
| `traits` | dict or `null` |
| `metadata` | `sdk_version` always; exposures from `get_experiment_flag`/`getExperimentFlag` add `experiment_id` (int). Python's metadata for a manual `track_event` has only `sdk_version` |
| `timestamp` | ms since epoch (docs: events older than 10 days or >24 h in the future are rejected; batch >2 MiB rejected whole) |

Sources: src python `analytics.py` `_buffer_event`/`_deliver`; node `build/esm/sdk/events.js`; js bundle `index.mjs` (EventProcessor) + `event-processor.d.ts` (`IEvent`); observed in all three captures. Response handling: Python treats any status <400 as delivered, Node and JS only 2xx (src python `_outcome_of`; node `events.js`; js bundle `s>=200&&s<300`), so a mock must answer events with **200**. 401/403 = key refused (SDK stops tracking and drops its buffer); 408/429/500/502/503/504 retried, up to 3 attempts per flush (src python `EVENTS_MAX_ATTEMPTS`, node `MAX_ATTEMPTS=3`; JS retries with exponential backoff, attempt count not read).

### 1.3 Batching, flushing, dedup (behaviour that decides whether a request ever appears)

| Fact | Value | Source |
|---|---|---|
| Default flush | every 10 s, or when buffer reaches 1000 events | src python `EventProcessorConfig` (`flush_interval_seconds=10`, `max_buffer_items=1000`); js `flushInterval=1e4, maxBuffer=1e3` |
| Events are batched | Yes; exposure + conversion tracked close together arrive in ONE POST | observed (all three) |
| Exposure only emitted when | flag exists AND enabled AND `experiment.in_experiment` true AND a `variant` key is present. Otherwise the SDK silently emits nothing. So against a mock/real server that does not return `metadata.experiment.in_experiment=true` + `variant`, NO exposure is ever sent | src python `get_experiment_flag`, node `getExperimentFlag`, js `getExperimentFlag` |
| Identity response fields the SDK needs for an exposure | `flags[].enabled`, `flags[].feature_state_value`, `flags[].feature.{id,name}`, `flags[].variant`, `flags[].metadata.experiment.{id,name,in_experiment}` | src python `models.py` `Flag.from_api_flag`, `ExperimentMetadata`; js `getFlags` |
| JS only emits an exposure if flags came from the server | `loadingState.source === SERVER` (not cache/defaults) | src js `getExperimentFlag` |
| Exposure dedup | per buffer window, identical (feature, identifier, value) exposures collapse to one in the buffer | src python `_buffered_exposure_keys`; docs: also deduplicated per identity server-side |
| Python flush in short scripts | **`flush_events()` and `close(timeout_seconds=5)` exist in 6.7.0** (docs mention only `max_buffer_items=1`). Client does not close itself at exit; unflushed events are lost | src python `flagsmith.py` |
| **PITFALL: official prompt's Python advice drops exposures** | With `EventProcessorConfig(max_buffer_items=1)`, `get_experiment_flag(...)` immediately followed by `track_event(...)` evicts the exposure ("Event buffer was full: dropped the 1 oldest events"). 0/6 runs sent the exposure; with the default buffer + `flush_events()` 6/6 sent it | observed: `spike/py_buffer_race.sh` |
| Node flush | `await flagsmith.flushEvents()` exists (docs only show `await close()`); `close(timeoutMs?)` also flushes | src node `index.js`; observed |
| Node `trackEvent` needs identifier | `trackEvent(name, {identifier, value})`; without `identifier` the event is sent with `identifier: null` (no join) | src node `index.js` |
| JS `trackEvent` identity | defaults to the identity set by `identify()` | src js `flagsmith-core.ts` |
| JS flush | `await flagsmith.flushEvents()`; `stop()`/`close()` also flush | src js |

### 1.4 What the grader should assert (derived)

An app is "instrumented" for experiment `onboarding_method` with metric event `E` iff the capture contains, for the same `identifier`:
(a) an event with `event == "$flag_exposure"` and `feature_name == "onboarding_method"` and a non-null `value` (variant key), and
(b) a later-or-same-batch event with `event == "E"` exactly (case-sensitive), from a request whose `X-Environment-Key` header (name matched case-insensitively) is the expected key.
The grader's fake identities response MUST include `metadata.experiment.in_experiment: true` and a `variant` key for the target flag, otherwise correct code looks broken.

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
| Browser bundle | `index.js` is UMD, sets `window.flagsmith` | n/a | n/a | observed (`spike/js/browser_spike.py`) |

Spike scripts: `spike/python/run.py`, `spike/node/run.mjs`, `spike/js/run_node.mjs`, `spike/js/browser_spike.py` (flag `spike_flag`, identity `spike-1`, event `spike_event`).

## 3. Interception: what is proven

| Stack | Design A: app pointed at mock via URL options; capture AT the mock (`spike/run_direct.sh`) | Design B: HTTPS MITM proxy for the DEFAULT hosts (`spike/run_mitm.sh`) |
|---|---|---|
| Node SDK (`@flagsmith/nodejs`) | PROVEN. identities + events captured | PROVEN with `NODE_USE_ENV_PROXY=1` + `HTTPS_PROXY` + `https_proxy` + `NODE_EXTRA_CA_CERTS=<mitm ca>` on Node 22.23.5 (prints an UNDICI-EHPA experimental warning). **Without `NODE_USE_ENV_PROXY=1`, `HTTPS_PROXY` is ignored: 0 requests captured** (observed) |
| JS SDK in Node (isomorphic) | PROVEN | PROVEN, same env as Node |
| Python SDK | PROVEN (default buffer + `flush_events()`; with `max_buffer_items=1` the exposure is missing, see pitfall) | PROVEN with `HTTPS_PROXY`+`https_proxy`+`REQUESTS_CA_BUNDLE`+`SSL_CERT_FILE` = mitm CA |
| JS SDK in Chromium (Playwright) | PROVEN. A page really served from `http://127.0.0.1:<port>` (python `http.server`) can call the mock on another loopback port with NO special flag (observed, `spike/js/browser_lna_test.py`, with and without `--disable-features=LocalNetworkAccessChecks`). Only a page Chromium does not treat as loopback (my first test used a Playwright `route.fulfill`ed page at a fake origin) is blocked ("Permission was denied ... loopback address space") and needs that flag. So: serve fixture apps from loopback; add the flag only if pages come from a non-loopback origin | PROVEN with `chromium.launch(proxy={"server": ...})` + `new_context(ignore_https_errors=True)` (no CA install needed) |

Observed gotchas:

- **Lowercase proxy vars win.** This sandbox sets lowercase `https_proxy` (agent proxy). Node/undici and Python `requests` read the lowercase variable first, so setting only `HTTPS_PROXY` silently routed traffic to the real internet (no capture; Python raised `FlagsmithAPIError`). The grader must set BOTH `HTTPS_PROXY` and `https_proxy` (and clear `NO_PROXY`/`no_proxy` if they list the target).
- In design B, the mitm addon (`spike/mitm_addon.py`) answers `*.flagsmith.com` itself (no upstream, no credentials). Pointing the SDKs at the real hosts through mitmproxy in forwarding mode was NOT run (no credentials); expect it to work the same since the proxy sees the cleartext requests, but that is UNVERIFIED.
- DNS-override / reverse-proxy fallback: NOT tried (not needed).
- Playwright python 1.65.2 could not use the preinstalled Chromium (asks for `playwright install`); `playwright==1.63.0` matches `/opt/pw-browsers` (chromium-1243).
- mitmproxy needs its CA only for non-browser clients; the CA is generated at `~/.mitmproxy/mitmproxy-ca-cert.pem` on first start.

**Which is more robust for the grader.** The two designs answer different questions:

- Design A is simplest (plain HTTP, no CA/proxy env, no per-stack proxy quirks, identical for all stacks, trivially JSONL at the mock) but it only sees traffic if the app-under-test honours a custom API/events URL. The official prompt (Cloud path) tells the agent to use the default hosts; agent-written code will not read a grader-chosen env var unless the task brief defines one. The events URL is also a SEPARATE option from the API URL in all three SDKs (`eventsApiUrl` / `events_api_url`, default `events.api.flagsmith.com`; src), so an app whose API URL comes from env but whose events URL is not wired still sends exposures and conversions to the real events host and Design A sees only the identities call: silently missing exposure/conversion. So A depends on agent cooperation (the thing spec section 7 task 3 wants to avoid).
- Design B captures the default hosts regardless of what the app code does, so it is the robust choice for **agent-written apps**. Cost: per-stack proxy/CA env (proven above) and Chromium launch options; apps that hardcode their own proxy/agent, or use a custom CA bundle, can bypass it.
- Recommendation: B (mitmproxy with a short-circuiting addon like `spike/mitm_addon.py`, which also needs no Flagsmith credentials in the grader) as the primary capture for agent-written apps; A as the cheap path for the grader's own known-good/known-broken fixture apps and as a cross-check when the app exposes `FLAGSMITH_API_URL`-style config. mitmproxy is required only when the app calls the real/default host.

## 4. Claude Code headless (Claude Code 2.1.332, `claude --help` + trivial runs)

| Fact | Value | Source |
|---|---|---|
| Headless flag | `-p` / `--print`; prompt as argument or stdin | `claude --help`; observed |
| Turn limit | `--max-turns N` (accepted but not listed in `--help` in 2.1.332). With `--max-turns 1` and a task needing 2 tool calls: JSON `subtype:"error_max_turns"`, `is_error:true`, `terminal_reason:"max_turns"`, `num_turns:2`, `result:null` | observed |
| JSON output | `--output-format json` (single result object) or `stream-json` (not exercised); `text` default | `--help`; observed json |
| Usage fields in JSON result | top-level `usage`: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, plus `server_tool_use`, `service_tier`, `iterations[]`; `total_cost_usd`; `modelUsage{<model>:{inputTokens,outputTokens,cacheReadInputTokens,cacheCreationInputTokens,costUSD,...}}`; `num_turns`, `duration_ms`, `duration_api_ms`, `session_id`, `subtype`, `is_error`, `result`, `stop_reason`, `terminal_reason`, `permission_denials` | observed (trivial run, haiku, cost about $0.003) |
| Budget cap | `--max-budget-usd <amount>` (print mode) | `--help` (not exercised) |
| Tool restriction | `--allowedTools "Bash(git *) Edit"` (comma/space list), `--disallowedTools`, `--tools "Bash,Edit,Read"` (`""` = none) | `--help` |
| Permission mode | `--permission-mode acceptEdits\|auto\|bypassPermissions\|manual\|dontAsk\|plan`; `--permission-prompts none` denies anything that would prompt; `--dangerously-skip-permissions` | `--help`; `dontAsk` + `--allowedTools Bash` run reached 2 turns with a tool_use stop (before max-turns hit); `permission_denials` not inspected |
| Model | `--model sonnet\|opus\|haiku\|<full id>`; `--fallback-model` | `--help`; observed `haiku` -> `claude-haiku-5-5` |
| No session files | `--no-session-persistence` (print mode) | `--help` |
| Other useful | `--bare` (skip hooks/CLAUDE.md/auto-memory, auth strictly `ANTHROPIC_API_KEY`), `--setting-sources`, `--settings`, `--append-system-prompt`, `--json-schema`, `--effort`, `--add-dir`, `--session-id` | `--help` |
| Project skill location | `<cwd>/.claude/skills/<name>/SKILL.md` (frontmatter `name`, `description`). A skill with description "Use when the user says PINGSKILL ..." placed there was auto-discovered in `claude -p` and its body followed (reply `SKILLWORD-42`, 3 turns) | observed |
| Agent Skills spec | SKILL.md with YAML frontmatter: `name` (<=64 chars, lowercase/digits/hyphens), `description` (<=1024), optional `license`, `compatibility`, `metadata`, `allowed-tools`; optional `scripts/`, `references/`, `assets/` | https://agentskills.io/specification |
| API key env var | `ANTHROPIC_API_KEY` (was unset in this sandbox; the run above authenticated through the sandbox's own session, so **API-key auth for CI is UNVERIFIED here**) | `--help` (`--bare` text); not testable here |
| Flagsmith-published skills repo | Not located/checked (GitHub access not enabled for this session). UNVERIFIED | n/a |

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
| Create metric | `flagsmith api api/v1/environments/<env key>/experiment-metrics/ -X POST --input -` with `{"name":"<n>","aggregation":"occurrence","direction":"up","definition":{"version":1,"event":"<event>"}}` (the only payload shown in the docs uses `"aggregation":"occurrence"`, `"direction":"up"`; Occurrence/Count/Sum/Mean are UI names, the API values for count/sum/mean and other directions are UNVERIFIED) | docs: set-up-with-a-coding-agent, create-metrics. No dedicated CLI subcommand (`flagsmith --help` has none) |
| Create experiment | `flagsmith api api/v1/environments/<env key>/experiments/ -X POST --input -` (i.e. `POST api/v1/environments/<env key>/experiments/`) `{"feature":<flag id>,"name":..,"hypothesis":..,"metrics":[{"metric":<metric id>,"expected_direction":"increase"}],"experiment_rollout":{"enabled":true,"rollout_percentage":100,"feature_state_value":{"type":"string","value":"control"},"multivariate_feature_state_values":[{"multivariate_feature_option":<variation id>,"percentage_allocation":50}]}}` | docs: set-up-with-a-coding-agent |
| **Start experiment** | `flagsmith api api/v1/environments/<env key>/experiments/<id>/start/ -X POST`, then check status is `running`. So starting IS documented via API/CLI (`flagsmith api`). The docs say only the Flagsmith **MCP server** cannot start experiments. **UNVERIFIED live (needs credentials + warehouse).** H7 stays PENDING as a contingency only until a live call succeeds | docs: set-up-with-a-coding-agent |
| Results | `POST .../experiments/<id>/results/refresh/` (allowed once per 5 min), `GET .../experiments/<id>/results/` | docs |
| Warehouse check | `GET api/v1/environments/<env key>/warehouse-connections/` must be non-empty; the events service rejects events for environments without one (a warehouse is a human prerequisite, H1) | docs |
| Running experiment | flag and variations locked; rollout % editable; an ended experiment cannot be restarted | docs: create-an-experiment |
| `flagsmith api` | `flagsmith api <path> [-X METHOD] [-F k=v] [-f k=v] [--input file\|-] [--sdk] [-i]`; typed `-F` builds JSON, POST implied | observed `--help` |
| Global flags | `--json`, `--jq <expr>`, `--no-input`, `--yes`, `-p/--project`, `-e/--environment`, `--organisation` | observed `--help` |
| Live calls (login, create flag/metric/experiment, delete) | **UNVERIFIED (needs credentials)**: no live CLI call was possible | n/a |

## 6. Official prompt

Extracted verbatim to `prompt/OFFICIAL_PROMPT.md` (SHA-256 `35ecba5b98c502c6aa94dccfc65ff6a9028a8672e01d02d2b07c8d1e7df7001d`,
retrieved 2026-11-26T15:49:58Z, source https://docs.flagsmith.com/experimentation/set-up-with-a-coding-agent); verify with `python3 prompt/verify_official_prompt.py`.
The interactive points (3 initial questions, login, project/environment choice, plan approval, test-traffic offer, stop-on-error) are listed in that file.

## 7. Rate limits and parallelism

| Fact | Value | Source |
|---|---|---|
| SDK endpoints (flags, identities, events) | "not rate limited, by design"; only monthly plan limits apply (Free plan: blocked when over plan limit after a warning email) | docs: administration-and-security/governance-and-compliance/system-limits |
| Management API (everything the CLI/`flagsmith api` calls) | default **500 requests per minute** (self-hosted: `USER_THROTTLE_RATE`). It is a per-user throttle, so all trials sharing one Master API key share this budget (the per-user scope is my inference from the variable name, not stated outright) | same page |
| Results refresh | once every 5 minutes per experiment | docs: set-up-with-a-coding-agent |
| Event acceptance window | timestamps within -10 days / +24 h; batch <= 2 MiB | docs: run-an-experiment |
| System limits | 1000 features/project, 500 segments/project, 2000 segment overrides/env | system-limits page |
| Recommendation | `max-parallel: 5` for the trial matrix (a trial agent plausibly makes tens of management calls; 5 concurrent stays far below 500/min); lower to 3 if any HTTP 429 appears in trial logs. Free-plan monthly SDK/event volume is a separate cap to check at the pilot (H6). Clean up sandbox flags after each trial (1000 features/project cap) | derived |

## 8. Not yet verified (needs credentials / human steps)

- Any live Flagsmith call: CLI login with a Master API key, create flag + keyed variation, metric, experiment, start, delete.
- Real identities response shape for a running experiment (the mock's shape is derived from SDK parsing code, not captured from the server).
- Real events endpoint response and rejection behaviour.
- Phase 0 acceptance: "one manual experiment created, started, with one exposure and one event" (needs H1-H3).
- Claude Code with `ANTHROPIC_API_KEY` auth in CI; `stream-json` output shape.

---

# Appendix: sample-app SDK verification (from the sample-apps phase)

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
- The exposure endpoint is separate from the flags API: events go to `https://events.api.flagsmith.com/` (`POST <events url>/v1/events`), configured via `eventsApiUrl` / `events_api_url`, NOT via the flags API base URL. A grader that mocks only `FLAGSMITH_API_URL` still sees flag requests, but events need the events URL pointed at the mock too. The reference apps expose this as optional `FLAGSMITH_EVENTS_URL` (server) / `VITE_FLAGSMITH_EVENTS_API` (React).
- `getExperimentFlag` / `get_experiment_flag` only emits the `$flag_exposure` event when the flag exists, is enabled, the identity is enrolled in a running experiment (`metadata.experiment.in_experiment == true` in the identities response) and the flag has a `variant`. Otherwise it behaves as a plain read and no exposure is sent. The exposure event `value` is the variant key (e.g. `"B"`), not the flag text value.
- Node and Python throw if `enableEvents` is not set when calling the experiment/track methods; `trackEvent`/`track_event` reject event names starting with `$`.
- Browser SDK `getExperimentFlag` returns `IFlagsmithFeature | null`; flag keys are lower-cased with spaces replaced by `_`. Node/Python SDKs require a server-side key only for local evaluation; remote evaluation (used here) accepts the key given.

Sources: `types.d.ts` and `src/flagsmith-core.ts` in the installed `@flagsmith/flagsmith` package; `sdk/index.ts`, `sdk/events.ts`, `sdk/types.ts` in the installed `@flagsmith/nodejs` package; `flagsmith/flagsmith.py` and `flagsmith/analytics.py` in the `flagsmith` wheel.

## Observed wire format (against a local mock, real SDKs)

- Flags: browser `GET <api>/identities/?identifier=<id>`; Node/Python `POST <api>/identities/` with `{"identifier": "<id>", "traits": []}`.
- Events: `POST <events>/v1/events` with `{"events": [{"event": "$flag_exposure"|"join_clicked", "feature_name", "identifier", "value", "traits", "metadata", "timestamp"}]}`. Exposure and conversion carry the same `identifier` in all three reference apps.
- Default flush interval is a timer (10 s in Python); the reference apps call flush right after the exposure and after the click so events are sent within the grader's wait windows.
