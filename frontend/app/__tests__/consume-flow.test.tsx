/**
 * End-to-end consume flow on the home page against msw-mocked API endpoints.
 *
 * One tap on a tile uses the item up (operator, 2026-09-22 and 2026-09-24 - presence, not
 * amounts): no sheet, no confirmation, the tile leaves at once and the header's Undo names what
 * just happened. "…" still opens the sheet - optimistic update, toast, rollback on error.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { StatusBanner } from '@/components/layout'
import Home from '../page'
import type { UndoPreview } from '@/types/consumption'
import type { InventoryItem } from '@/types/inventory'

function inDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

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
  // Tomorrow, so it is a tile on the going-stale shelf rather than a dot in its area
  expiry_date: inDays(1),
  expiry_source: 'calculated',
  opened_date: null,
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2024-01-01T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
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
        {/* AppShell renders this above every page; the flow needs it to show a failed tap */}
        <StatusBanner />
        <Home />
      </ToastProvider>
    </QueryClientProvider>
  )
}

const TILE = 'Oat Milk, going stale'

function tile() {
  return screen.queryByRole('button', { name: TILE })
}

/**
 * The endpoints every render of the page asks for, plus the ones a test adds. The test's come
 * first: within one `server.use` the first matching handler wins, so they override the defaults.
 */
function api(...handlers: Parameters<typeof server.use>) {
  server.use(
    ...handlers,
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null))
  )
}

async function openSheetAndTap(label: string) {
  fireEvent.click(await screen.findByRole('button', { name: 'More for Oat Milk' }))
  const sheet = await screen.findByRole('dialog', { name: 'Oat Milk' })
  fireEvent.click(within(sheet).getByRole('button', { name: label }))
}

describe('One tap on the tile', () => {
  it('uses the item up at once, with no sheet and no toast', async () => {
    let stock: InventoryItem[] = [MILK]
    const bodies: unknown[] = []
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
      http.post(`${API_URL}/inventory/:id/consume`, async ({ request }) => {
        bodies.push(await request.json())
        stock = []
        return HttpResponse.json({ ...MILK, current_quantity: 0, status: 'empty' })
      })
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: TILE }))

    await waitFor(() => expect(tile()).not.toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(bodies).toEqual([{ quantity: 1000 }]))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('rolls back and says why when a tap fails', async () => {
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
      http.post(`${API_URL}/inventory/:id/consume`, () =>
        HttpResponse.json({ detail: 'Oat Milk has been thrown away' }, { status: 409 })
      )
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: TILE }))

    // Both the toast and the banner are alerts now, so name what it should say
    expect(await screen.findByText('Oat Milk has been thrown away')).toBeInTheDocument()
    await waitFor(() => expect(tile()).toBeInTheDocument())
  })

  it('the header Undo then names the tap, which is the confirmation and the way back', async () => {
    let undoable: UndoPreview | null = null
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json(undoable ? [] : [MILK])),
      http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(undoable)),
      http.post(`${API_URL}/inventory/:id/consume`, () => {
        undoable = {
          batch_id: 'b1',
          logged_at: '2026-09-22T08:00:00+00:00',
          steps: [
            {
              inventory_item_id: 'item-milk',
              product_name: 'Oat Milk',
              unit: 'dl',
              action: 'use_full',
              quantity_consumed: 1000,
            },
          ],
        }
        return HttpResponse.json({ ...MILK, current_quantity: 0, status: 'empty' })
      })
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: TILE }))

    expect(
      await screen.findByRole('button', { name: 'Undo Finished · Oat Milk' })
    ).toBeEnabled()
  })
})

describe('The sheet behind "…"', () => {
  it('sends the amount without waiting, and confirms with a toast', async () => {
    let stored: InventoryItem = MILK
    let releaseConsume: () => void = () => {}
    const consumeReleased = new Promise<void>((resolve) => {
      releaseConsume = resolve
    })
    const consumeBodies: unknown[] = []

    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([stored])),
      http.post(`${API_URL}/inventory/:id/consume`, async ({ request, params }) => {
        consumeBodies.push({ id: params.id, body: await request.json() })
        await consumeReleased
        stored = { ...MILK, current_quantity: 500, status: 'partial', opened_date: '2024-02-01' }
        return HttpResponse.json(stored)
      })
    )

    renderHome()
    await openSheetAndTap('½ · 500 dl')

    // The sheet closes at once; the tile stays, since half is still there
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(consumeBodies).toEqual([{ id: 'item-milk', body: { quantity: 500 } }])
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(tile()).toBeInTheDocument()

    releaseConsume()

    expect(await screen.findByRole('status')).toHaveTextContent('Consumed 500 dl · Oat Milk')
  })

  it('removes a used-up item as soon as Done is tapped', async () => {
    let releaseConsume: () => void = () => {}
    const consumeReleased = new Promise<void>((resolve) => {
      releaseConsume = resolve
    })
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
      http.post(`${API_URL}/inventory/:id/consume`, async () => {
        await consumeReleased
        return HttpResponse.json({ ...MILK, current_quantity: 0, status: 'empty' })
      })
    )

    renderHome()
    await openSheetAndTap('Done')

    // Optimistically empty, so the fridge hides it before the server answers
    await waitFor(() => expect(tile()).not.toBeInTheDocument())
    expect(screen.getByText(/No items found/i)).toBeInTheDocument()

    releaseConsume()
    expect(await screen.findByRole('status')).toHaveTextContent('Used up · Oat Milk')
  })

  it('rolls back and shows the server error when consuming fails', async () => {
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
      http.post(`${API_URL}/inventory/:id/consume`, () =>
        HttpResponse.json({ detail: 'Cannot consume 500 - only 100 available' }, { status: 400 })
      )
    )

    renderHome()
    await openSheetAndTap('Done')

    expect(
      await screen.findByText('Cannot consume 500 - only 100 available')
    ).toBeInTheDocument()
    await waitFor(() => expect(tile()).toBeInTheDocument())
  })
})

describe('When a tap does not land', () => {
  it('leaves it in the banner to retry, because a toast would be gone in five seconds', async () => {
    let reachable = false
    const attempts: unknown[] = []
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
      http.post(`${API_URL}/inventory/:id/consume`, async ({ request }) => {
        attempts.push(await request.json())
        if (!reachable) return HttpResponse.json({ detail: 'Nope' }, { status: 503 })
        return HttpResponse.json({ ...MILK, current_quantity: 0, status: 'empty' })
      })
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: TILE }))

    expect(await screen.findByText('Consume failed')).toBeInTheDocument()

    reachable = true
    fireEvent.click(screen.getByRole('button', { name: 'Retry Consume' }))

    await waitFor(() => expect(screen.queryByText('Consume failed')).not.toBeInTheDocument())
    // The same request, sent again - not a second one
    expect(attempts).toEqual([{ quantity: 1000 }, { quantity: 1000 }])
  })
})
