/**
 * Receipts list (MVP-R8): find a receipt you left, and see which one still needs you.
 */

import React from 'react'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import ReceiptsPage from '../page'
import type { ReceiptStatus, ReceiptSummary } from '@/types/receipt'

function summary(overrides: Partial<ReceiptSummary> = {}): ReceiptSummary {
  return {
    id: 'r1',
    store_chain: 's-group',
    purchase_date: '2026-09-02',
    processing_status: 'completed' as ReceiptStatus,
    error: null,
    queued_at: '2026-09-16T10:00:00Z',
    processing_started_at: '2026-09-16T10:00:03Z',
    items_extracted: 41,
    items_matched: 3,
    extraction_method: 'text',
    fallback_reason: null,
    created_at: '2026-09-16T10:00:00Z',
    ...overrides,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage(receipts: ReceiptSummary[]) {
  server.use(http.get(`${API_URL}/receipts`, () => HttpResponse.json(receipts)))
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ReceiptsPage />
    </QueryClientProvider>
  )
}

const rows = () => screen.getAllByRole('listitem')

describe('ReceiptsPage', () => {
  it('names the store, the date and what was read, and opens the receipt', async () => {
    renderPage([summary()])

    const link = await screen.findByRole('link', { name: /S-group/ })
    expect(link).toHaveAttribute('href', '/receipt/r1')
    expect(within(link).getByText(/2\.9\.2026/)).toBeInTheDocument()
    expect(within(link).getByText('41 items, 3 already known')).toBeInTheDocument()
  })

  it.each([
    ['queued', /waiting to be read/i],
    ['processing', /reading/i],
    ['completed', /waiting for review/i],
    ['failed', /could not read/i],
    ['confirmed', /added to stock/i],
  ] as [ReceiptStatus, RegExp][])('shows a %s receipt as such', async (status, label) => {
    renderPage([summary({ processing_status: status })])

    expect(await screen.findByText(label)).toBeInTheDocument()
  })

  it('flags the one that is read but not yet added', async () => {
    renderPage([
      summary({ id: 'r-done', processing_status: 'confirmed' }),
      summary({ id: 'r-waiting', processing_status: 'completed' }),
    ])

    await screen.findByText(/added to stock/i)
    const waiting = rows()[1]
    expect(within(waiting).getByText(/waiting for review/i)).toBeInTheDocument()
  })

  it('shows why a receipt failed instead of an item count', async () => {
    renderPage([summary({ processing_status: 'failed', error: 'LLM timed out' })])

    expect(await screen.findByText('LLM timed out')).toBeInTheDocument()
  })

  it('keeps the order the API gave, newest first', async () => {
    renderPage([summary({ id: 'newer' }), summary({ id: 'older' })])

    await screen.findAllByRole('listitem')
    expect(rows().map((row) => within(row).getByRole('link').getAttribute('href'))).toEqual([
      '/receipt/newer',
      '/receipt/older',
    ])
  })

  it('points an empty list at the two ways in', async () => {
    renderPage([])

    expect(await screen.findByText(/no receipts yet/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /scan one here/i })).toHaveAttribute(
      'href',
      '/scan'
    )
  })
})
