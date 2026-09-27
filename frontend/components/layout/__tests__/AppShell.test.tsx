/**
 * The rail is the only navigation in the app (MVP-P1), so every destination has to be there
 * and the current one has to be obvious.
 */

import React from 'react'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell, DESTINATIONS } from '../AppShell'

let pathname = '/'
jest.mock('next/navigation', () => ({ usePathname: () => pathname }))

beforeEach(() => {
  pathname = '/'
})

function renderShell() {
  // The shell carries the status banner (H45), which reads the query cache; in the app it is
  // always inside the providers.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AppShell>
        <main>the page</main>
      </AppShell>
    </QueryClientProvider>
  )
}

describe('AppShell', () => {
  it('renders the page it wraps', () => {
    renderShell()

    expect(screen.getByText('the page')).toBeInTheDocument()
  })

  it('offers stock and receipts', () => {
    renderShell()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: /stock/i })).toHaveAttribute('href', '/')
    expect(within(nav).getByRole('link', { name: /receipts/i })).toHaveAttribute(
      'href',
      '/receipts'
    )
  })

  it('has no Scan button: scanning starts from Receipts (Q32)', () => {
    renderShell()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).queryByRole('link', { name: /scan/i })).not.toBeInTheDocument()
    expect(DESTINATIONS.map((d) => d.href)).not.toContain('/scan')
  })

  it('tucks Settings behind an unobtrusive "More" button, not a destination (Q33)', () => {
    renderShell()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    const more = within(nav).getByRole('link', { name: 'More' })
    expect(more).toHaveAttribute('href', '/settings')
    expect(more.textContent).toContain('⋯')
    // A full touch target, in both the top bar and the rail
    expect(more.className).toMatch(/min-h-touch/)
    expect(more.className).toMatch(/min-w-touch/)
    expect(DESTINATIONS.map((d) => d.href)).not.toContain('/settings')
  })

  it('marks More current on the settings page', () => {
    pathname = '/settings'
    renderShell()

    expect(screen.getByRole('link', { name: 'More' })).toHaveAttribute('aria-current', 'page')
  })

  it('offers Gone, the only screen that shows what is no longer in stock', () => {
    renderShell()

    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(within(nav).getByRole('link', { name: /gone/i })).toHaveAttribute('href', '/gone')
  })

  it.each([
    ['/', /stock/i],
    ['/receipts', /receipts/i],
    ['/gone', /gone/i],
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
