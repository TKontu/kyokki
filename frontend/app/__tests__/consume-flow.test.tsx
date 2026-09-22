/**
 * End-to-end consume flow on the home page against msw-mocked API endpoints.
 *
 * One tap on the card consumes (operator, 2026-09-22): no sheet, no confirmation, the quantity
 * bar moves at once and the header's Undo names what just happened. "…" still opens the sheet
 * with every amount - optimistic update, toast, rollback on error.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import Home from '../page'
import type { UndoPreview } from '@/types/consumption'
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

describe('One tap on the card', () => {
  it('consumes a quarter at once, with no sheet and no toast', async () => {
    let stored: InventoryItem = MILK
    const bodies: unknown[] = []
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([stored])),
      http.post(`${API_URL}/inventory/:id/consume`, async ({ request }) => {
        bodies.push(await request.json())
        stored = { ...MILK, current_quantity: 750, status: 'opened' }
        return HttpResponse.json(stored)
      })
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: 'Consume 250 dl of Oat Milk' }))

    await waitFor(() => expect(remaining('750 of 1000 dl remaining')).toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(bodies).toEqual([{ quantity: 250 }]))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('consumes again on every tap', async () => {
    let stored: InventoryItem = MILK
    const bodies: unknown[] = []
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([stored])),
      http.post(`${API_URL}/inventory/:id/consume`, async ({ request }) => {
        const { quantity } = (await request.json()) as { quantity: number }
        bodies.push(quantity)
        stored = { ...stored, current_quantity: stored.current_quantity - quantity, status: 'opened' }
        return HttpResponse.json(stored)
      })
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: 'Consume 250 dl of Oat Milk' }))
    await waitFor(() => expect(remaining('750 of 1000 dl remaining')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Consume 250 dl of Oat Milk' }))

    await waitFor(() => expect(remaining('500 of 1000 dl remaining')).toBeInTheDocument())
    await waitFor(() => expect(bodies).toEqual([250, 250]))
  })

  it('rolls back and says why when a tap fails', async () => {
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
      http.post(`${API_URL}/inventory/:id/consume`, () =>
        HttpResponse.json({ detail: 'Oat Milk has been thrown away' }, { status: 409 })
      )
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: 'Consume 250 dl of Oat Milk' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Oat Milk has been thrown away')
    await waitFor(() => expect(remaining('1000 of 1000 dl remaining')).toBeInTheDocument())
  })

  it('the header Undo then names the tap, which is the confirmation and the way back', async () => {
    let undoable: UndoPreview | null = null
    api(
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([MILK])),
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
              action: 'use_partial',
              quantity_consumed: 250,
            },
          ],
        }
        return HttpResponse.json({ ...MILK, current_quantity: 750, status: 'opened' })
      })
    )

    renderHome()
    fireEvent.click(await screen.findByRole('button', { name: 'Consume 250 dl of Oat Milk' }))

    expect(
      await screen.findByRole('button', { name: 'Undo −250 dl · Oat Milk' })
    ).toBeEnabled()
  })
})

describe('The sheet behind "…"', () => {
  it('updates the list immediately, sends the amount, and confirms with a toast', async () => {
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
    api(
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
    api(
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
