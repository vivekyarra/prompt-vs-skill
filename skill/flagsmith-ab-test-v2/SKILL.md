---
name: flagsmith-ab-test
description: Run a Flagsmith A/B test end to end - multivariate flag with keyed variation, conversion metric, experiment, exposure and conversion tracking in code, verification in the real runtime, then read the results, decide against an agreed rule and, with human approval, ship the winner and verify it. Use when asked to A/B test a UI change, add a Flagsmith experiment, record exposures and conversions, or roll out an experiment winner.
---

# Flagsmith A/B test

Goal: a running experiment where every visitor who sees a variation is recorded as exposed and every conversion is recorded for the same visitor; later, a decision from the results and a verified rollout.

Working rules:
- Follow the steps in order. Batch independent commands into one shell call; read only the files you need.
- Token budget: every CLI read uses `--json --jq <expr>` and prints only the fields needed; never dump full objects.
- If unsure of an SDK method or import, read https://docs.flagsmith.com/experimentation/run-an-experiment once (language tab) and copy its imports.
- Steps 1-7 build and verify the experiment, then stop and report. Steps 8-10 run only after the experiment has collected data.

## 0. Decide first
Flag name (snake_case), control value, variation value, variation key (same text as the value), conversion event name (case-sensitive, identical in metric and code), the real action that counts as success (click or submit, not a page view), and the decision rule (default in step 8). Use the values the task gives you.

## 1. Setup
- Management calls use `FLAGSMITH_API_KEY` (Master key); the SDK uses the environment's client key (`api_key`). Management URLs address an environment by that key (`<env>` = `api/v1/environments/<client key>`). Never commit keys.
- `flagsmith --version` (v2+). If missing: `npm install -g @flagsmith/cli`. Find ids: `flagsmith project list --json --jq '.[]|{id,name}'`, `flagsmith environment list --project <project> --json` (or read `flagsmith.json`).
- Send requests as `echo '{...}' | flagsmith api <path> -X POST --input - --json --jq .id`.
- Warehouse: `<env>/warehouse-connections/` normally lists one. If empty, say so; do not invent data.

## 2. Visitor identity
Reuse the app's visitor id (user id, session id, anonymous id). It must be stable across reloads and identical for exposure and conversion. If none exists, create one anonymous id once and persist it; never a new random id per call.

## 3. Flag with a keyed variation (project level)
```
POST api/v1/projects/<project id>/features/
{"name":"<flag>","type":"MULTIVARIATE","initial_value":"<control>","default_enabled":true}
```
Take `.id` (flag id). Then:
```
POST api/v1/projects/<project id>/features/<flag id>/mv-options/
{"type":"unicode","string_value":"<variation>","key":"<variation_key>","default_percentage_allocation":0,"feature":<flag id>}
```
Take `.id` (variation id; step 9 needs it). A variation without a key records no exposures. Leave allocation at 0; the experiment sets the split.

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
Returns 201, `status:"created"`; take `.id`. Control gets the remainder. Starting locks the flag, so finish flag edits first, then `POST <env>/experiments/<experiment id>/start/`. Expect 200 and `status:"running"`. Exposures record only while running, so start before verifying. If it refuses, report why and still finish the code.

## 6. Wire the code
Minimum SDK versions: JavaScript/React `@flagsmith/flagsmith` >= 12.4.0, Node `@flagsmith/nodejs` >= 9.1.0, Python `flagsmith` >= 6.3.0, Java `flagsmith-java-client` >= 8.2.0, Go `flagsmith-go-client/v5` >= 5.3.0, Flutter `flagsmith` >= 6.2.0.

**Use the right package and entry point for the runtime that sends the events:**
- Browser JavaScript / React: `import flagsmith from '@flagsmith/flagsmith'` and, for React, `import { FlagsmithProvider, useExperiment, useFlagsmith } from '@flagsmith/flagsmith/react'`.
- Node server: `import { Flagsmith } from '@flagsmith/nodejs'`.
- Python: `from flagsmith import Flagsmith`.
- In browser code do NOT import `@flagsmith/flagsmith/isomorphic` (Node-oriented) and do NOT pass a `fetch` option (e.g. `window.fetch`) into `init`: an unbound `fetch` is rejected, the SDK swallows the error, flags load, and every event is silently lost.

Initialize with the client key and events ENABLED (Node/Python throw otherwise). Events have their own URL, default `https://events.api.flagsmith.com/` (`eventsApiUrl` / `events_api_url`); a custom API URL does not redirect events, so set both.

**Exposure: call the experiment method where the visitor sees the variation, after identifying them, on every render/request (never memoise). Branch on `flag.value`**, not `.variant` (the bucket name, `control` for control). Fall back to the control value if the call fails.
```js
import flagsmith from '@flagsmith/flagsmith';                            // browser JS
await flagsmith.init({ environmentID: CLIENT_KEY, enableEvents: true });
await flagsmith.identify(visitorId);
const flag = flagsmith.getExperimentFlag('<flag>');                      // sync, after init + identify
```
```jsx
import { useExperiment } from '@flagsmith/flagsmith/react';              // inside <FlagsmithProvider flagsmith={flagsmith} options={{ environmentID, enableEvents: true }}>
const flag = useExperiment('<flag>');
```
```js
import { Flagsmith } from '@flagsmith/nodejs';                           // Node
const fs = new Flagsmith({ environmentKey: KEY, enableEvents: true });
const flag = await fs.getExperimentFlag('<flag>', visitorId);
```
```python
from flagsmith import Flagsmith
fs = Flagsmith(environment_key=KEY, enable_events=True)   # EventProcessorConfig(events_api_url=...) only for a non-default events URL
flag = fs.get_experiment_flag("<flag>", identifier=visitor_id)
```

**Conversion: fire in the handler of the real action, not on page load, with the same visitor id.**
```js
flagsmith.trackEvent('<event>', { value: 1 });                    // JS/React (identified user)
await fs.trackEvent('<event>', { identifier: visitorId });        // Node
```
```python
fs.track_event("<event>", identifier=visitor_id)
```
Event names starting with `$` are rejected. Java, Go and Flutter have equivalent calls.

**Flush**: short-lived scripts and tests flush before exiting: JavaScript `await flagsmith.flushEvents()`, Node/Java `close()`, Go `FlushEvents(ctx)`, Python `fs.flush_events()` then `fs.close()`. Keep the default Python buffer: do NOT set `max_buffer_items=1`, which can evict the exposure when `track_event` follows `get_experiment_flag`. Servers and browsers flush on a timer (about 10 s), so app code needs no explicit flush.

## 7. Verify once, in the real runtime
Send no bulk traffic. Verify in the runtime that sends the events; a Node script cannot show a browser-only failure.
- **Browser app**: start it, run one headless-browser script (Playwright) with a fresh visitor that performs the real action, waits past the flush, and prints the requests whose URL contains `/v1/events`. Check their bodies.
- **Server app**: start it, call the real route twice for one fresh visitor id, perform the action once; read the SDK debug or request log. A standalone script flushes first.
- Confirm: an exposure for `<flag>` with identity X, the conversion `<event>` with the same X, event name equal to the metric's, and a second load for X gives the same value.

Fix and repeat once if it fails. If events are missing, check: experiment running, keys, events URL, import path (section 6), no `fetch` option, experiment method on every view. When it passes, report and stop until step 8.

## 8. Read the results and decide (after data has accumulated; never peek to stop early)
Agree the rule up front with the human. Default: win probability >= 95% and a credible interval excluding zero, at the planned sample size; otherwise the answer is `inconclusive`: recommend continuing, do not ship.
```
flagsmith api <env>/experiments/<id>/results/refresh/ -X POST     # once per 5 minutes (429 = wait)
flagsmith api <env>/experiments/<id>/results/ --json --jq '.results|{as_of,is_final,m:[.payload.metrics[]|{metric_id,arms:(.variants|map_values({exposed:.n,converted:.sum})),inference}]}'
```
Check `as_of` is newer than the refresh. Print per-arm exposed and converted counts and the inference block only, then state ship-variation, ship-control or inconclusive against the rule.

## 9. Ship, only with approval (production safety gate)
- Rehearse in the development environment first. NEVER ship, end or change a production experiment without the human's explicit approval: show the numbers, the decision and the exact command, then wait for an explicit "yes". No yes, no change.
- Control wins, or stop with no winner: `echo '{"rollout_decision":"control"}' | flagsmith api <env>/experiments/<id>/complete/ -X POST --input - --json --jq '{status,rollout_decision}'`
- Variation wins: body `{"rollout_decision":"variant","rollout_variant":<integer variation id>}` (the id from step 3; the key string is rejected). Only `control` and `variant` are valid decisions.
- Completion is final (no restart). Rollback line: ship control with the same call, or create a new experiment with the previous allocation.

## 10. Verify the rollout and finish
The flag follows a few seconds after completion; retry for up to about 3 minutes. Read the flag for 3-5 fresh identities (new ids, `get_identity_flags` or `getIdentityFlags`, reading `.value`); all must return the winner's value. Print `PASS` or `FAIL` with the values.
Finish with one summary line: flag, decision, counts, rollout status, PASS/FAIL, and the number of Flagsmith CLI calls made.

## Common mistakes
- Plain flag reads (`getValue`, `get_flags`, `useFlags`) record no exposure; use the experiment method.
- Isomorphic import or a `fetch` option in browser code; verifying only in Node when a browser sends the events.
- Branching on `.variant`; experiment not started; conversion on page load or a different identity; a new random id per request.
- Events not enabled or not flushed in a short process; wrong events host; variations without keys; event-name typos vs. the metric.
- Never put a server-side or Master key in browser code; do not commit `.env`.
- Stopping early on a lucky interval, or shipping production without a "yes".
