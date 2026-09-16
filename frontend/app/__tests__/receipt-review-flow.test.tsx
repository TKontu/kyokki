/**
 * The home page tells you a receipt is waiting and links to its review (MVP-R5 + R7).
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import Home from '../page'
import type { Receipt } from '@/types/receipt'

const WAITING = {
  id: 'r-waiting',
  store_chain: 's-group',
  purchase_date: '2026-09-02',
  processing_status: 'completed',
  items_extracted: 41,
  items_matched: 0,
  created_at: '2026-09-16T18:37:18Z',
  items: [],
} as unknown as Receipt

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderHome() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <Home />
      </ToastProvider>
    </QueryClientProvider>
  )
}

it('offers the waiting receipt above an empty stock list', async () => {
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([])),
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([WAITING]))
  )

  renderHome()

  const link = await screen.findByRole('link', { name: /1 receipt waiting to review/i })
  expect(link).toHaveAttribute('href', '/receipt/r-waiting')
  expect(await screen.findByText(/no items found/i)).toBeInTheDocument()
})

it('stays quiet when there is nothing to review', async () => {
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([])),
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([]))
  )

  renderHome()

  expect(await screen.findByText(/no items found/i)).toBeInTheDocument()
  expect(screen.queryByText(/waiting to review/i)).not.toBeInTheDocument()
})
