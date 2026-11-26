# Sample app: React (Vite)

A one-page app: a heading, a paragraph and a single **Join** button (`#join-btn`).
Clicking it shows "Thanks for joining!".

## Install and run

```
npm ci
npm start        # builds, then serves on http://localhost:5173
npm test         # page renders + Join button exists
```

## Visitor identity

Visitor identity: a visitor ID is generated once and stored in `localStorage` under the key `visitor_id` (see `src/visitor.js`, `getVisitorId()`).
