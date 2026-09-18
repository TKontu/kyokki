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
