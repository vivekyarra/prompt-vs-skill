import React, { useEffect, useState } from 'react'
import flagsmith from '@flagsmith/flagsmith'
import { getVisitorId } from './visitor.js'

const CONTROL_TEXT = 'Join'
const FLAG = import.meta.env.VITE_FLAGSMITH_FLAG || 'join_button_text'
const CLIENT_KEY = import.meta.env.VITE_FLAGSMITH_CLIENT_KEY
const API = import.meta.env.VITE_FLAGSMITH_API || 'https://edge.api.flagsmith.com/api/v1/'
const EVENTS_API = import.meta.env.VITE_FLAGSMITH_EVENTS_API // optional; SDK default if unset

export default function App() {
  const [joined, setJoined] = useState(false)
  const [buttonText, setButtonText] = useState(CONTROL_TEXT)
  const [visitorId] = useState(getVisitorId) // resolved once per page load

  useEffect(() => {
    if (!CLIENT_KEY) return // no key: stay on the control text
    let cancelled = false
    flagsmith
      .init({
        environmentID: CLIENT_KEY,
        api: API,
        identity: visitorId, // the app's existing visitor id
        enableEvents: true,
        ...(EVENTS_API ? { eventProcessorConfig: { eventsApiUrl: EVENTS_API } } : {}),
        onError: () => {},
      })
      .then(() => {
        // Experiment method: reads the flag AND records the exposure for this identity.
        const flag = flagsmith.getExperimentFlag(FLAG)
        flagsmith.flushEvents().catch(() => {}) // send the exposure now, not on the timer
        if (!cancelled && flag && typeof flag.value === 'string' && flag.value) {
          setButtonText(flag.value)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [visitorId])

  const onJoin = () => {
    setJoined(true)
    if (CLIENT_KEY) {
      // Conversion: only on click, with the same identity as the exposure.
      flagsmith.trackEvent('join_clicked', { identifier: visitorId })
      flagsmith.flushEvents().catch(() => {})
    }
  }

  return (
    <main style={{ fontFamily: 'sans-serif', maxWidth: 480, margin: '4rem auto' }}>
      <h1>Join our community</h1>
      <p>Get weekly tips and updates delivered to your inbox.</p>
      <button id="join-btn" data-visitor={visitorId} onClick={onJoin}>
        {buttonText}
      </button>
      {joined && <p id="thanks">Thanks for joining!</p>}
    </main>
  )
}
