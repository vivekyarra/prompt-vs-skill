import crypto from 'node:crypto'
import express from 'express'
import cookieParser from 'cookie-parser'
import { Flagsmith } from '@flagsmith/nodejs'

export const app = express()
app.use(express.json())
app.use(cookieParser())

const FLAG = process.env.FLAGSMITH_FLAG || 'join_button_text'
const CONTROL_TEXT = 'Join'

// Server-side key: only ever read here, on the server. Never sent to the browser.
const flagsmith = process.env.FLAGSMITH_SERVER_KEY
  ? new Flagsmith({
      environmentKey: process.env.FLAGSMITH_SERVER_KEY,
      apiUrl: process.env.FLAGSMITH_API_URL || 'https://edge.api.flagsmith.com/api/v1/',
      enableEvents: true,
      ...(process.env.FLAGSMITH_EVENTS_URL
        ? { eventProcessorConfig: { eventsApiUrl: process.env.FLAGSMITH_EVENTS_URL } }
        : {}),
    })
  : null

// Visitor identity: a long-lived cookie `vid`, set by this middleware.
app.use((req, res, next) => {
  let vid = req.cookies.vid
  if (!vid) {
    vid = crypto.randomUUID()
    res.cookie('vid', vid, { maxAge: 365 * 24 * 3600 * 1000, httpOnly: true, sameSite: 'lax' })
  }
  req.vid = vid
  next()
})

function page(buttonText) {
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Join our community</title></head>
<body style="font-family:sans-serif;max-width:480px;margin:4rem auto">
  <h1>Join our community</h1>
  <p>Get weekly tips and updates delivered to your inbox.</p>
  <button id="join-btn">${buttonText}</button>
  <p id="thanks" style="display:none">Thanks for joining!</p>
  <script>
    document.getElementById('join-btn').addEventListener('click', async () => {
      await fetch('/join', { method: 'POST' })
      document.getElementById('thanks').style.display = 'block'
    })
  </script>
</body>
</html>`
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

app.get('/', async (req, res) => {
  let text = CONTROL_TEXT
  if (flagsmith) {
    try {
      // Experiment method: reads the flag AND records the exposure for this identity.
      const flag = await flagsmith.getExperimentFlag(FLAG, req.vid)
      await flagsmith.flushEvents() // send the exposure now, not on the timer
      if (typeof flag.value === 'string' && flag.value) text = flag.value
    } catch (err) {
      console.error('flagsmith error:', err.message)
    }
  }
  res.type('html').send(page(escapeHtml(text)))
})

app.post('/join', async (req, res) => {
  if (flagsmith) {
    try {
      // Conversion: only on click, with the same identity as the exposure.
      flagsmith.trackEvent('join_clicked', { identifier: req.vid })
      await flagsmith.flushEvents()
    } catch (err) {
      console.error('flagsmith error:', err.message)
    }
  }
  res.json({ ok: true })
})
