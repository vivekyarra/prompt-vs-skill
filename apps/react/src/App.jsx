import React, { useState } from 'react'
import { getVisitorId } from './visitor.js'

export default function App() {
  const [joined, setJoined] = useState(false)
  const visitorId = getVisitorId()

  return (
    <main style={{ fontFamily: 'sans-serif', maxWidth: 480, margin: '4rem auto' }}>
      <h1>Join our community</h1>
      <p>Get weekly tips and updates delivered to your inbox.</p>
      <button id="join-btn" data-visitor={visitorId} onClick={() => setJoined(true)}>
        Join
      </button>
      {joined && <p id="thanks">Thanks for joining!</p>}
    </main>
  )
}
