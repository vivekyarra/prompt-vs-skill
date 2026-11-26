import test from 'node:test'
import assert from 'node:assert'
import { app } from '../app.js'

test('page renders with a Join button and POST /join works', async () => {
  const server = app.listen(0)
  const base = `http://127.0.0.1:${server.address().port}`
  try {
    const res = await fetch(base + '/')
    assert.equal(res.status, 200)
    assert.match(res.headers.get('set-cookie') || '', /vid=/)
    const html = await res.text()
    assert.match(html, /id="join-btn"/)
    const join = await fetch(base + '/join', { method: 'POST' })
    assert.equal(join.status, 200)
  } finally {
    server.close()
  }
})
