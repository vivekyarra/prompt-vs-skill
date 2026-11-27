import test from 'node:test'
import assert from 'node:assert'
import { app } from '../app.js'

test('page renders with a signup button and POST /signup works', async () => {
  const server = app.listen(0)
  const base = `http://127.0.0.1:${server.address().port}`
  try {
    const res = await fetch(base + '/')
    assert.equal(res.status, 200)
    assert.match(res.headers.get('set-cookie') || '', /vid=/)
    assert.match(await res.text(), /id="signup"/)
    const r = await fetch(base + '/signup', { method: 'POST' })
    assert.equal(r.status, 200)
  } finally {
    server.close()
  }
})
