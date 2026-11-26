---
name: flagsmith-ab-test
description: Set up a Flagsmith A/B test in an existing app end to end - multivariate flag with keyed variations, conversion metric, experiment, exposure and conversion tracking in code, and a local verification. Use when asked to A/B test a UI change, add a Flagsmith experiment, or record exposures and conversion events with Flagsmith.
---

# Flagsmith A/B test

Goal: a running Flagsmith A/B test where every visitor who sees a variation is recorded as exposed, and every conversion is recorded against the same visitor. Use the Flagsmith CLI with `--json` for every Flagsmith write. Keep command output small (`--jq <expr>` filters it).

Do not guess commands or flags. If one below is marked "verify", run `flagsmith <command> --help` first.

## 0. Inputs

Decide before touching anything:
- **Flag name** (snake_case), **control value**, **variation value**, **variation key**.
- **Conversion event name** (case-sensitive; use the exact same string in the metric and in code).
- **The real user action** that counts as success (a click, a submit, a purchase), not a page view.

## 1. Prerequisites

1. `flagsmith --version` (need v2+). If missing, install via the official install script, Homebrew, or npm.
2. Credentials: management commands read `FLAGSMITH_API_KEY` (an admin/master API key). SDKs use an environment key (`FLAGSMITH_ENVIRONMENT_KEY` for `flagsmith eval`). If no key is in the environment, run `flagsmith init` interactively; otherwise do not prompt.
3. Bind the repo: `flagsmith init --project <project> --environment <environment key>` (verify flags with `flagsmith init --help`). It writes `flagsmith.json` (no secrets). Use `flagsmith project list --json` and `flagsmith environment list --project <project> --json` to find ids.
4. Experiments need a data warehouse on the environment: `flagsmith api api/v1/environments/<environment key>/warehouse-connections/` should return one. If none exists, report this clearly; do not fake data.

## 2. Find the visitor identity

Search the app for how it already identifies a visitor: a user id, session id, anonymous id cookie/localStorage value, `identify`/analytics calls, auth middleware. Use that mechanism.

- The identifier must be stable across page loads for the same visitor and the same value must be used for exposure and conversion.
- If the app has none, create one anonymous id once, persist it (cookie or localStorage in a browser, request/session store on a server), and reuse it. Never generate a fresh random id on each call.

## 3. Create the flag with a keyed variation

```
flagsmith feature create <flag> --value <control> --enabled --json
flagsmith feature variant add <flag> --value <variation> --key <variation_key> --weight 0 --json
flagsmith feature get <flag> --json
```

Every variation needs a `--key`; without one, exposures are not recorded. Confirm the key in the `get` output. Weight is set by the experiment's traffic split, so leave it at 0.

## 4. Create the metric

Create a metric whose event name is the conversion event, as an occurrence/count metric, via `flagsmith api` with `POST api/v1/environments/<environment key>/experiment-metrics/` and a JSON body on stdin (`--input -`). Inspect the metric payload shape from the Flagsmith docs ("Create metrics") or the API response to an empty/invalid request; do not invent field names. Add `--json`. Record the returned metric id.

## 5. Create and start the experiment

- Create: `POST api/v1/environments/<environment key>/experiments/` with the flag, the metric as primary, 100% of traffic in the test and an even split between control and variation. Take the body shape from the docs ("Create an experiment") or the API's validation errors.
- Start: `POST api/v1/environments/<environment key>/experiments/<id>/start/`. Starting locks the flag, so finish any variation edits first.
- Results can be read later with `GET .../experiments/<id>/results/` (refresh at most every 5 minutes).

If the CLI/API refuses to start it, leave it created, say so in your summary, and continue with the code.

## 6. Wire the code

Install an SDK version that supports experiments: JavaScript/React `@flagsmith/flagsmith` >= 12.4.0, Node `@flagsmith/nodejs` >= 9.1.0, Python `flagsmith` >= 6.3.0, Java `flagsmith-java-client` >= 8.2.0, Go `flagsmith-go-client/v5` >= 5.3.0, Flutter `flagsmith` >= 6.2.0.

Browser code uses the client-side environment key; server code uses the server-side key. Read keys from configuration or environment variables, never hard-code them.

**Exposure: read the flag with the experiment method, once, where the visitor sees the variation, after identifying them.**

```js
// JavaScript (identify the visitor first)
const flag = flagsmith.getExperimentFlag('<flag>');
// React
const flag = useExperiment('<flag>');
// Node
const flag = await flagsmith.getExperimentFlag('<flag>', visitorId);
```
```python
flag = flagsmith.get_experiment_flag("<flag>", identifier=visitor_id)
```
Render from `flag.value`, with the control value as the fallback if the call fails.

**Conversion: fire on the real action's handler, not on page load.**

```js
flagsmith.trackEvent('<event>', { value: 1 });                       // JS/React
flagsmith.trackEvent('<event>', { identifier: visitorId });          // Node
```
```python
flagsmith.track_event("<event>", identifier=visitor_id)
```
Java, Go and Flutter have equivalent `getExperimentFlag` / `trackEvent` calls; check the SDK's docs for exact parameters.

If you must read the flag with a normal call, record exposure explicitly at display time with `trackExposureEvent` (Python: `track_exposure_event`), only for identities in the test.

**Flush events** before a short-lived process exits: JavaScript/Flutter `await flagsmith.flushEvents()`, Node/Java `close()`, Go `FlushEvents(ctx)`. Python has no flush call; use `EventProcessorConfig(max_buffer_items=1)` for scripts and tests. Events are otherwise batched (about every 10 seconds). Make sure event sending is enabled in SDK init options.

## 7. Verify (required before finishing)

Use only general tools. Do not send bulk or simulated traffic; one visit and one click is enough.

1. Start the app with the real environment key.
2. Make one visit as a fresh visitor, then perform the action once (click the real button / submit the real form).
3. Confirm, from app logs, SDK debug output, browser network requests, or a short script, that:
   - an exposure for `<flag>` was sent with identity X,
   - the conversion event `<event>` was sent with the same identity X,
   - the event name matches the metric exactly,
   - events were flushed (not just buffered).
4. Reload and confirm the same identity X (and so the same variation) is used.
5. `flagsmith feature get <flag> --json` still shows the keyed variation and the experiment is running.

If anything does not match, fix it and repeat step 7.

## Common mistakes

- Plain flag reads (`getValue`, `get_flags`, `useFlags`) record no exposure. Use the experiment method.
- Firing the conversion on page load instead of the action inflates the metric.
- Different identities for exposure and conversion break attribution. Use one visitor id for both.
- Unstable identifiers (new random id per request or reload) put one person in many buckets.
- Not enabling and flushing events: buffered events are lost when the process exits.
- Variations without keys: exposures are not recorded.
- Event name typos or case differences between the metric and the code.
- Never ship a server-side environment key or admin API key to the browser; only the client-side key goes in front-end code.
- Do not commit keys. `flagsmith.json` is safe to commit; `.env` files are not.

## Finish

Summarize in a short paragraph: flag, variation key, metric, experiment status, files changed, identity mechanism used, and what the verification showed.
