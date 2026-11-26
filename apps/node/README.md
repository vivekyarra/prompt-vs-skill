# Sample app: Node (Express)

A one-page app: a heading, a paragraph and a single **Join** button (`#join-btn`).
Clicking it sends `POST /join` and shows "Thanks for joining!".

## Install and run

```
npm ci
npm start        # serves on http://localhost:3000
npm test         # page renders + Join button exists + POST /join works
```

## Visitor identity

Visitor identity: a visitor ID is generated once and stored in a long-lived cookie named `vid`, set by the middleware in `app.js` (available as `req.vid`).
