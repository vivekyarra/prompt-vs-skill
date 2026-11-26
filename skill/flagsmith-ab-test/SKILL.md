---
name: flagsmith-ab-test
description: Set up a Flagsmith A/B test in an existing app end to end - multivariate flag with keyed variation, conversion metric, experiment (created and started), exposure and conversion tracking in code, and one local verification. Use when asked to A/B test a UI change, add a Flagsmith experiment, or record exposures and conversion events with Flagsmith.
---

# Flagsmith A/B test

Goal: a running experiment where every visitor who sees a variation is recorded as exposed, and every conversion is recorded for the same visitor.

Working rules (they save turns):
- Follow the happy path below in order. Do not browse docs or explore unless a command fails.
- Batch independent commands into one shell call (`&&`, or several commands in a script). Read only the files you need.
- Use `--json` on Flagsmith CLI calls and `--jq <expr>` to keep output small.
- After ONE successful verification (step 7), stop, print `DONE` and a short summary. Do not re-verify or polish.

## 0. Decide first
Flag name (snake_case), control value, variation value, variation key (use the same text as the value), conversion event name (case-sensitive, identical in the metric and in code), and the real user action that counts as success (a click or submit, not a page view). Use the values the task gives you.

## 1. Setup
- Management calls use `FLAGSMITH_API_KEY` (a Master API key). The app's SDK uses the environment's client key (the `api_key` of the environment). Management URLs address an environment by that client key (`<env>` below = `api/v1/environments/<client key>`). Never commit keys; read them from env/config.
- `flagsmith --version` (v2+). If missing: `npm install -g @flagsmith/cli`. Find ids: `flagsmith project list --json`, `flagsmith environment list --project <project> --json` (or read `flagsmith.json` if present).
- Send management requests with `flagsmith api <path> -X POST --input - --json` and the JSON body on stdin (`echo '{...}' | flagsmith api ...`). The response JSON contains the new `id`; read it with `--jq .id`.
- Warehouse: `flagsmith api <env>/warehouse-connections/` normally already lists one (auto-created). Only if the list is empty, say so; do not fake data.

## 2. Visitor identity
Reuse how the app already identifies a visitor (user id, session id, anonymous id cookie/localStorage). It must be stable across reloads and identical for exposure and conversion. If none exists, create one anonymous id once, persist it, and reuse it. Never make a new random id per call.

## 3. Flag with a keyed variation (project level, one call each)
```
POST api/v1/projects/<project id>/features/
{"name":"<flag>","type":"MULTIVARIATE","initial_value":"<control>","default_enabled":true}
```
Take `.id` (flag id). Then:
```
POST api/v1/projects/<project id>/features/<flag id>/mv-options/
{"type":"unicode","string_value":"<variation>","key":"<variation_key>","default_percentage_allocation":0,"feature":<flag id>}
```
Take `.id` (variation id); the response echoes `key`. A variation without a key records no exposures. Leave allocation at 0; the experiment sets the split. (The CLI `flagsmith feature create` / `feature variant add --key` is an equivalent route; the API calls above are the verified ones.)

## 4. Metric
```
POST <env>/experiment-metrics/
{"name":"<event>","aggregation":"occurrence","direction":"up","definition":{"version":1,"event":"<event>"}}
```
Take `.id` (metric id). Metrics belong to one environment.

## 5. Create and start the experiment
```
POST <env>/experiments/
{"feature":<flag id>,"name":"<name>","hypothesis":"<hypothesis>",
 "metrics":[{"metric":<metric id>,"expected_direction":"increase"}],
 "experiment_rollout":{"enabled":true,"rollout_percentage":100,
  "feature_state_value":{"type":"string","value":"<control>"},
  "multivariate_feature_state_values":[{"multivariate_feature_option":<variation id>,"percentage_allocation":50}]}}
```
Returns 201 with `status:"created"`; take `.id`. The variation gets its percentage and control gets the rest. Starting locks the flag, so finish flag edits first, then:
```
POST <env>/experiments/<experiment id>/start/
```
Expect 200 and `status:"running"`. Exposures are only recorded while the experiment is running, so start it before verifying. If it refuses to start, report why and still finish the code.

## 6. Wire the code
Minimum SDK versions: JavaScript/React `@flagsmith/flagsmith` >= 12.4.0, Node `@flagsmith/nodejs` >= 9.1.0, Python `flagsmith` >= 6.3.0, Java `flagsmith-java-client` >= 8.2.0, Go `flagsmith-go-client/v5` >= 5.3.0, Flutter `flagsmith` >= 6.2.0.

Initialize the SDK with the client key and events ENABLED (Node/Python throw otherwise). The events service has its own URL, separate from the flags API URL: default `https://events.api.flagsmith.com/` (option `eventsApiUrl` / `events_api_url`). Setting only the API URL does not redirect events; if the app uses a custom or local API URL, set the events URL too.

**Exposure: use the experiment method once, where the visitor sees the variation, after identifying them. Branch on `flag.value`** (the variation's value, e.g. the control or variation text). Do NOT branch on `.variant`, which is the bucket name (`control` for the control bucket) and need not equal your value. Fall back to the control value if the call fails.
```js
const flag = flagsmith.getExperimentFlag('<flag>');                      // JS (after identify)
const flag = useExperiment('<flag>');                                    // React
const flag = await flagsmith.getExperimentFlag('<flag>', visitorId);     // Node
```
```python
from flagsmith import Flagsmith
fs = Flagsmith(environment_key=KEY, enable_events=True)   # add event_processor_config=EventProcessorConfig(events_api_url=...) only for a non-default events URL
flag = fs.get_experiment_flag("<flag>", identifier=visitor_id)
```

**Conversion: fire in the handler of the real action, not on page load, with the same visitor id.**
```js
flagsmith.trackEvent('<event>', { value: 1 });                    // JS/React (uses the identified user)
flagsmith.trackEvent('<event>', { identifier: visitorId });       // Node
```
```python
fs.track_event("<event>", identifier=visitor_id)
```
Event names starting with `$` are rejected. Java, Go and Flutter have equivalent `getExperimentFlag` / `trackEvent` calls.

**Flush before a short-lived process exits**: JavaScript/Flutter/Node `await flagsmith.flushEvents()`, Node/Java `close()`, Go `FlushEvents(ctx)`, Python `fs.flush_events()` then `fs.close()`. Keep the default Python buffer: do NOT set `max_buffer_items=1`; with it, a `track_event` right after `get_experiment_flag` can evict the exposure from the buffer and it is never sent. Long-running servers and browsers flush on a timer (about every 10 seconds); flush explicitly only in scripts and tests.

## 7. Verify once, then stop
Do not send bulk or simulated traffic. In one script/run:
1. Use a fresh visitor id; call the experiment-flag method, then perform the action once, then flush.
2. Check the output (SDK debug log, request log, or a short script) shows: an exposure for `<flag>` with identity X, the conversion `<event>` with the same identity X, event name equal to the metric's, and that events were flushed. Optionally `flagsmith api <env>/experiments/<id>/` shows `running`.
3. Confirm a second call for the same id gives the same value.

If something does not match, fix and repeat once. When it passes: print `DONE` and the summary. Stop; take no further steps.

## Common mistakes
- Plain flag reads (`getValue`, `get_flags`, `useFlags`) record no exposure; use the experiment method. If you must read plainly, call `trackExposureEvent` (Python `track_exposure_event`) at display time.
- Branching on `.variant` instead of `.value`.
- Experiment not started, so no exposure is sent.
- Conversion on page load, or a different identity for exposure and conversion.
- A new random id per request or reload.
- Events not enabled, or not flushed in a short process; events URL left at the wrong host.
- Variations without keys; event-name typos or case differences vs. the metric.
- Never put a server-side key or Master API key in browser code; do not commit `.env` (`flagsmith.json` holds no secrets).

## Finish
In a short paragraph: flag, variation key, metric, experiment status, files changed, identity mechanism, and what verification showed.
