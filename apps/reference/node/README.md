# Reference integration: Node + Flagsmith (correct)

Copy of `apps/node` with a correct Flagsmith experiment integration (`@flagsmith/nodejs` 9.5.0).

## Install and run

```
npm ci
FLAGSMITH_SERVER_KEY=... npm start   # serves on http://localhost:3000
npm test
```

| Variable | Meaning | Default |
|---|---|---|
| `FLAGSMITH_SERVER_KEY` | server-side environment key (without it the app shows the control text and sends nothing) | none |
| `FLAGSMITH_FLAG` | flag name | `join_button_text` |
| `FLAGSMITH_API_URL` | Flagsmith API base URL (point at a local emulator) | `https://edge.api.flagsmith.com/api/v1/` |
| `FLAGSMITH_EVENTS_URL` | events API base URL (optional) | SDK default `https://events.api.flagsmith.com/` |

## Visitor identity

Visitor identity: a visitor ID is generated once and stored in a long-lived cookie named `vid`, set by the middleware in `app.js` (available as `req.vid`).

## What is wired

- `new Flagsmith({ enableEvents: true })`; `GET /` calls `getExperimentFlag(flag, req.vid)` (records the exposure) then `flushEvents()`.
- Button text = flag value; control text `Join` on any failure.
- `POST /join` calls `trackEvent('join_clicked', { identifier: req.vid })` + `flushEvents()`.
- The server key is read only in `app.js` and never rendered into the page.
