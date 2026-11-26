# Verified facts (sample apps / SDK methods)

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
