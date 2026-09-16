/**
 * The home page banner: what is waiting to be reviewed (MVP-R7 entry point).
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ReceiptsBanner } from '../ReceiptsBanner'
import type { Receipt, ReceiptStatus } from '@/types/receipt'

function receipt(id: string, status: ReceiptStatus, extra: Partial<Receipt> = {}): Receipt {
  return {
    id,
    store_chain: 's-group',
    purchase_date: '2026-09-02',
    processing_status: status,
    items_extracted: 41,
    items_matched: 0,
    created_at: `2026-09-16T10:00:00Z`,
    items: [],
    ...extra,
  } as Receipt
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderBanner(receipts: Receipt[]) {
  server.use(http.get(`${API_URL}/receipts`, () => HttpResponse.json(receipts)))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <ReceiptsBanner />
    </QueryClientProvider>
  )
}

describe('ReceiptsBanner', () => {
  it('links to a receipt waiting to be reviewed', async () => {
    renderBanner([receipt('r1', 'completed')])

    const link = await screen.findByRole('link', { name: /1 receipt waiting to review/i })
    expect(link).toHaveAttribute('href', '/receipt/r1')
  })

  it('counts several waiting receipts and sends you to the list to choose', async () => {
    renderBanner([
      receipt('new', 'completed', { created_at: '2026-09-16T12:00:00Z' }),
      receipt('old', 'completed', { created_at: '2026-09-15T12:00:00Z' }),
    ])

    const link = await screen.findByRole('link', { name: /2 receipts waiting to review/i })
    expect(link).toHaveAttribute('href', '/receipts')
  })

  it('says a receipt is being read, without a link', async () => {
    renderBanner([receipt('r1', 'processing')])

    expect(await screen.findByText(/reading a receipt/i)).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('links a failed receipt so it can be read again', async () => {
    renderBanner([receipt('r1', 'failed', { error: 'LLM timed out' })])

    const link = await screen.findByRole('link', { name: /could not be read/i })
    expect(link).toHaveAttribute('href', '/receipt/r1')
  })

  it('shows nothing when every receipt is confirmed', async () => {
    const { container } = { container: document.body }
    renderBanner([receipt('r1', 'confirmed')])

    await waitFor(() => expect(container.querySelectorAll('a')).toHaveLength(0))
    expect(screen.queryByText(/waiting to review|reading a receipt|could not be read/i)).toBeNull()
  })
})
