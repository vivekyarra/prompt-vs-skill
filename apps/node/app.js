import crypto from 'node:crypto'
import express from 'express'
import cookieParser from 'cookie-parser'

export const app = express()
app.use(express.json())
app.use(cookieParser())

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

app.get('/', (req, res) => {
  res.type('html').send(page('Join'))
})

app.post('/join', (req, res) => {
  res.json({ ok: true })
})
