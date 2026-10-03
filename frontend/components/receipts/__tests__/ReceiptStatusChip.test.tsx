/**
 * Where a receipt is in its life, in kitchen words (MVP-R8).
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { ReceiptStatusChip } from '../ReceiptStatusChip'

describe('ReceiptStatusChip', () => {
  it.each([
    ['uploaded', 'Not read yet'],
    ['queued', 'Waiting to be read'],
    ['processing', 'Reading'],
    ['completed', 'Waiting for review'],
    ['failed', 'Could not read'],
    ['confirmed', 'Added to stock'],
  ])('labels %s as %p', (status, label) => {
    render(<ReceiptStatusChip status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  // The old fallback was `CHIPS.uploaded`, which told the cook an unfamiliar status meant "Not
  // read yet" -- a statement about the receipt that nothing had established (H04).
  it('shows a status it does not know raw, instead of claiming it is unread', () => {
    render(<ReceiptStatusChip status="archived" />)
    expect(screen.getByText('archived')).toBeInTheDocument()
    expect(screen.queryByText('Not read yet')).not.toBeInTheDocument()
  })
})

describe('ReceiptStatusChip: display language (Post-MVP frontier item 13, phase 3)', () => {
  beforeEach(() => {
    window.localStorage.setItem('kyokki.language', 'fi')
  })
  afterEach(() => {
    window.localStorage.clear()
  })

  it.each([
    ['uploaded', 'Ei vielä luettu'],
    ['queued', 'Odottaa lukemista'],
    ['processing', 'Luetaan'],
    ['completed', 'Odottaa tarkistusta'],
    ['failed', 'Ei voitu lukea'],
    ['confirmed', 'Lisätty varastoon'],
  ])('labels %s as %p in Finnish', (status, label) => {
    render(<ReceiptStatusChip status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('shows a status it does not know raw, in Finnish mode too', () => {
    render(<ReceiptStatusChip status="archived" />)
    expect(screen.getByText('archived')).toBeInTheDocument()
  })
})
