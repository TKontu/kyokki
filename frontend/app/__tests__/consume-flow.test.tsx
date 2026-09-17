/**
 * End-to-end consume flow on the home page against msw-mocked API endpoints:
 * list -> Consume -> sheet -> ½ -> optimistic list update -> toast (or rollback on error).
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import Home from '../page'
import type { InventoryItem } from '@/types/inventory'

const MILK: InventoryItem = {
  id: 'item-milk',
  product_master_id: 'prod-milk',
  product_name: 'Oat Milk',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: null,
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 1000,
  unit: 'dl',
  status: 'sealed',
  purchase_date: '2024-01-01',
  expiry_date: '2099-03-01',
  expiry_source: 'calculated',
  opened_date: null,
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2024-01-01T10:00:00Z',
  consumed_at: null,
}

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

function remaining(label: string) {
  return screen.queryByRole('progressbar', { name: label })
}

async function openSheetAndTap(label: string) {
  fireEvent.click(await screen.findByRole('button', { name: /consume/i }))
  const sheet = await screen.findByRole('dialog', { name: 'Oat Milk' })
  fireEvent.click(within(sheet).getByRole('button', { name: label }))
}

describe('Consume flow', () => {
  it('updates the list immediately, sends the amount, and confirms with a toast', async () => {
    let stored: InventoryItem = MILK
    let releaseConsume: () => void = () => {}
    const consumeReleased = new Promise<void>((resolve) => {
      releaseConsume = resolve
    })
    const consumeBodies: unknown[] = []

    server.use(
      http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([stored])),
      http.post(`${API_URL}/inventory/:id/consume`, async ({ request, params }) => {
        consumeBodies.push({ id: params.id, body: await request.json() })
        await consumeReleased
        stored = { ...MILK, current_quantity: 500, status: 'partial', opened_date: '2024-02-01' }
        return HttpResponse.json(stored)
      })
    )

    renderHome()
    expect(await screen.findByRole('progressbar', { name: '1000 of 1000 dl remaining' })).toBeInTheDocument()

    await openSheetAndTap('½ · 500 dl')

    // Optimistic: the list shows the new amount while the request is still pending
    await waitFor(() => expect(remaining('500 of 1000 dl remaining')).toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(consumeBodies).toEqual([{ id: 'item-milk', body: { quantity: 500 } }])
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    releaseConsume()

    expect(await screen.findByRole('status')).toHaveTextContent('Consumed 500 dl · Oat Milk')
    expect(remaining('500 of 1000 dl remaining')).toBeInTheDocument()
  })

  it('removes a used-up item from the list as soon as Done is tapped', async () => {
    let releaseConsume: () => void = () => {}
    const consumeReleased = new Promise<void>((resolve) => {
      releaseConsume = resolve
    })
    server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
      http.post(`${API_URL}/inventory/:id/consume`, async () => {
        await consumeReleased
        return HttpResponse.json({ ...MILK, current_quantity: 0, status: 'empty' })
      })
    )

    renderHome()
    expect(await screen.findByText('Oat Milk')).toBeInTheDocument()

    await openSheetAndTap('Done')

    // Optimistically empty, so the stock view hides it before the server answers
    await waitFor(() => expect(screen.queryByText('Oat Milk')).not.toBeInTheDocument())
    expect(screen.getByText(/No items found/i)).toBeInTheDocument()

    releaseConsume()
    expect(await screen.findByRole('status')).toHaveTextContent('Used up · Oat Milk')
  })

  it('rolls the list back and shows the server error when consuming fails', async () => {
    server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
      http.post(`${API_URL}/inventory/:id/consume`, () =>
        HttpResponse.json({ detail: 'Cannot consume 500 - only 100 available' }, { status: 400 })
      )
    )

    renderHome()
    expect(await screen.findByRole('progressbar', { name: '1000 of 1000 dl remaining' })).toBeInTheDocument()

    await openSheetAndTap('½ · 500 dl')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Cannot consume 500 - only 100 available'
    )
    await waitFor(() =>
      expect(remaining('1000 of 1000 dl remaining')).toBeInTheDocument()
    )
    expect(remaining('500 of 1000 dl remaining')).not.toBeInTheDocument()
  })
})
