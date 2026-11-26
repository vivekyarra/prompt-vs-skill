# Reference integration: Python + Flagsmith (correct)

Copy of `apps/python` with a correct Flagsmith experiment integration (`flagsmith` 6.7.0).

## Install and run

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
FLAGSMITH_SERVER_KEY=... python app.py   # serves on http://localhost:5000
python -m pytest
```

| Variable | Meaning | Default |
|---|---|---|
| `FLAGSMITH_SERVER_KEY` | server-side environment key (without it the app shows the control text and sends nothing) | none |
| `FLAGSMITH_FLAG` | flag name | `join_button_text` |
| `FLAGSMITH_API_URL` | Flagsmith API base URL (point at a mock) | `https://edge.api.flagsmith.com/api/v1/` |
| `FLAGSMITH_EVENTS_URL` | events API base URL (optional) | SDK default `https://events.api.flagsmith.com/` |

## Visitor identity

Visitor identity: a visitor ID is generated once and stored in a long-lived cookie named `vid`, set by the `before_request` hook in `app.py` (available as `g.vid`).

## What is wired

- `Flagsmith(enable_events=True)`; `GET /` calls `get_experiment_flag(flag, g.vid)` (records the exposure) then `flush_events()`.
- Button text = flag value; control text `Join` on any failure.
- `POST /join` calls `track_event('join_clicked', identifier=g.vid)` + `flush_events()`.
- The server key is read only in `app.py` and never rendered into the page.
