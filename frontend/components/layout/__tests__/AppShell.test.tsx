/**
 * The rail is the only navigation in the app (MVP-P1), so every destination has to be there
 * and the current one has to be obvious.
 */

import React from 'react'
import { render, screen, within } from '@testing-library/react'
import { AppShell } from '../AppShell'

let pathname = '/'
jest.mock('next/navigation', () => ({ usePathname: () => pathname }))

beforeEach(() => {
  pathname = '/'
})

function renderShell() {
  render(
    <AppShell>
      <main>the page</main>
    </AppShell>
  )
}

describe('AppShell', () => {
  it('renders the page it wraps', () => {
    renderShell()

    expect(screen.getByText('the page')).toBeInTheDocument()
  })

  it('offers stock, scan and receipts', () => {
    renderShell()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: /stock/i })).toHaveAttribute('href', '/')
    expect(within(nav).getByRole('link', { name: /scan/i })).toHaveAttribute('href', '/scan')
    expect(within(nav).getByRole('link', { name: /receipts/i })).toHaveAttribute(
      'href',
      '/receipts'
    )
  })

  it.each([
    ['/', /stock/i],
    ['/scan', /scan/i],
    ['/receipts', /receipts/i],
  ])('marks %s as the current page', (path, name) => {
    pathname = path
    renderShell()

    expect(screen.getByRole('link', { name })).toHaveAttribute('aria-current', 'page')
  })

  it('keeps Receipts current while a receipt is open', () => {
    pathname = '/receipt/3c28b17b-0000-0000-0000-000000000000'
    renderShell()

    expect(screen.getByRole('link', { name: /receipts/i })).toHaveAttribute(
      'aria-current',
      'page'
    )
    expect(screen.getByRole('link', { name: /stock/i })).not.toHaveAttribute('aria-current')
  })

  it('marks nothing current on a page that is not a destination', () => {
    pathname = '/components-demo'
    renderShell()

    expect(screen.queryByRole('link', { current: 'page' })).not.toBeInTheDocument()
  })
})
