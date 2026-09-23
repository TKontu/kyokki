/**
 * Clearing the expired shelf.
 *
 * The destructive action of the pair: it throws food away, in bulk, on one tap. So it confirms
 * first, and says out loud what it records. The way back is the header's Undo, which takes the
 * whole cleared shelf back as one step.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import ClearExpiredSheet from '../ClearExpiredSheet'
import type { InventoryItem } from '@/types/inventory'

function makeItem(overrides: Partial<InventoryItem> = {}): InventoryItem {
  return {
    id: 'item-1',
    product_master_id: 'prod-1',
    product_name: 'Ground beef',
    category: 'meat',
    category_name: 'Meat & Poultry',
    category_icon: '🥩',
    receipt_id: null,
    initial_quantity: 400,
    current_quantity: 400,
    unit: 'g',
    status: 'sealed',
    purchase_date: '2024-01-01',
    expiry_date: '2024-01-10',
    expiry_source: 'calculated',
    opened_date: null,
    batch_number: null,
    location: 'main_fridge',
    notes: null,
    created_at: '2024-01-01T10:00:00Z',
    consumed_at: null,
    opened_shelf_life_days: null,
    avg_piece_grams: null,
    ...overrides,
  }
}

/** Dates relative to today, so the ages below do not rot - and no fake timers, which fight
 *  msw and the query client's polling. */
function daysAgo(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() - days)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${String(date.getDate()).padStart(2, '0')}`
}

const EXPIRED = [
  makeItem({ expiry_date: daysAgo(5) }),
  makeItem({ id: 'item-2', product_name: 'Sour cream', expiry_date: daysAgo(1) }),
]

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function mockApi() {
  const calls: { path: string; ids: string[] }[] = []
  server.use(
    http.post(`${API_URL}/inventory/:action`, async ({ request, params }) => {
      const body = (await request.json()) as { ids: string[] }
      calls.push({ path: String(params.action), ids: body.ids })
      return HttpResponse.json({ changed: body.ids.length, refused: 0, missing: 0 })
    })
  )
  return calls
}

function renderSheet(items = EXPIRED, onClose = jest.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ClearExpiredSheet items={items} open onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  return onClose
}

describe('ClearExpiredSheet', () => {
  it('names the count and lists what would go, with ages', () => {
    renderSheet()

    expect(screen.getByText('Clear 2 expired items?')).toBeInTheDocument()
    expect(screen.getByText('Ground beef')).toBeInTheDocument()
    expect(screen.getByText('5 days ago')).toBeInTheDocument()
    expect(screen.getByText('Yesterday')).toBeInTheDocument()
  })

  it('says what it records, because that is the number the app exists for', () => {
    renderSheet()

    expect(screen.getByText(/records them as thrown away/i)).toBeInTheDocument()
  })

  it('does nothing until the destructive button is tapped', () => {
    const calls = mockApi()
    const onClose = renderSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(calls).toEqual([])
    expect(onClose).toHaveBeenCalled()
  })

  it('throws them away in one request', async () => {
    const calls = mockApi()
    renderSheet()

    fireEvent.click(screen.getByRole('button', { name: /Yes, throw away/ }))

    await waitFor(() => expect(calls).toHaveLength(1))
    // One call, not one per item: clearing a shelf is a single transaction.
    expect(calls[0]).toEqual({ path: 'discard', ids: ['item-1', 'item-2'] })
    expect(await screen.findByText('Thrown away · 2 items')).toBeInTheDocument()
    // No Undo of its own on the toast: the header's Undo takes the whole shelf back
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
  })

  it('keeps the sheet open and says so when the clear fails', async () => {
    server.use(
      http.post(`${API_URL}/inventory/discard`, () =>
        HttpResponse.json({ detail: 'Nope' }, { status: 500 })
      )
    )
    const onClose = renderSheet()

    fireEvent.click(screen.getByRole('button', { name: /Yes, throw away/ }))

    expect(await screen.findByText('Could not clear 2 items')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('renders nothing when there is nothing to clear', () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <ToastProvider>
          <ClearExpiredSheet items={[]} open onClose={jest.fn()} />
        </ToastProvider>
      </QueryClientProvider>
    )

    expect(container.querySelector('[role="dialog"]')).toBeNull()
  })
})
