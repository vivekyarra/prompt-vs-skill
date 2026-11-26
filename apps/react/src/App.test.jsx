import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import App from './App.jsx'

describe('App', () => {
  it('renders heading and a Join button', () => {
    render(<App />)
    expect(screen.getByRole('heading')).toBeInTheDocument()
    expect(document.getElementById('join-btn')).toBeInTheDocument()
  })

  it('shows the thank-you message after clicking Join', () => {
    render(<App />)
    fireEvent.click(document.getElementById('join-btn'))
    expect(screen.getByText('Thanks for joining!')).toBeInTheDocument()
  })
})
