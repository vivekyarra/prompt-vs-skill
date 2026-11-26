# Sample app: Python (Flask)

A one-page app: a heading, a paragraph and a single **Join** button (`#join-btn`).
Clicking it sends `POST /join` and shows "Thanks for joining!".

## Install and run

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python app.py    # serves on http://localhost:5000
python -m pytest # page renders + Join button exists + POST /join works
```

## Visitor identity

Visitor identity: a visitor ID is generated once and stored in a long-lived cookie named `vid`, set by the `before_request` hook in `app.py` (available as `g.vid`).
