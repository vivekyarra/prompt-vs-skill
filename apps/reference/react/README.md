# Reference integration: React + Flagsmith (correct)

Copy of `apps/react` with a correct Flagsmith experiment integration (`@flagsmith/flagsmith` 12.6.0).

## Install and run

```
npm ci
VITE_FLAGSMITH_CLIENT_KEY=... npm start   # builds, then serves on http://localhost:5173
npm test
```

Vite inlines `VITE_*` variables at **build** time, so set them when running `npm start`/`npm run build`.

| Variable | Meaning | Default |
|---|---|---|
| `VITE_FLAGSMITH_CLIENT_KEY` | client-side environment key (without it the app shows the control text and sends nothing) | none |
| `VITE_FLAGSMITH_FLAG` | flag name | `join_button_text` |
| `VITE_FLAGSMITH_API` | Flagsmith API base URL (point at a local emulator) | `https://edge.api.flagsmith.com/api/v1/` |
| `VITE_FLAGSMITH_EVENTS_API` | events API base URL (optional) | SDK default `https://events.api.flagsmith.com/` |

## Visitor identity

Visitor identity: a visitor ID is generated once and stored in `localStorage` under the key `visitor_id` (see `src/visitor.js`, `getVisitorId()`).

## What is wired

- `init({ identity: visitorId, enableEvents: true })`, then `getExperimentFlag(flag)` (records the exposure) and `flushEvents()`.
- Button text = flag value; control text `Join` if the flag/keys are unavailable.
- `trackEvent('join_clicked', { identifier: visitorId })` + `flushEvents()` only on click.
