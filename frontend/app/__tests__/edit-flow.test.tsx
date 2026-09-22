/**
 * End-to-end edit flow on the home page against msw-mocked endpoints (MVP-S4):
 * … -> Edit item -> move to the freezer -> Save -> list regroups; then Mark as gone -> the item
 * disappears, and the header's Undo brings it back.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import Home from '../page'
import type { InventoryItem } from '@/types/inventory'

const PEAS: InventoryItem = {
  id: 'item-peas',
  product_master_id: 'prod-peas',
  product_name: 'Peas',
  category: 'frozen',
  category_name: 'Frozen Foods',
  category_icon: '🧊',
  receipt_id: null,
  initial_quantity: 500,
  current_quantity: 500,
  unit: 'g',
  status: 'sealed',
  purchase_date: '2026-09-14',
  expiry_date: '2099-03-13',
  expiry_source: 'calculated',
  opened_date: null,
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2026-09-14T10:00:00Z',
  consumed_at: null,
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** Edit lives behind the card's "…" since consuming became one tap (2026-09-22). */
function openEdit(name: string) {
  fireEvent.click(screen.getByRole('button', { name: `More for ${name}` }))
  fireEvent.click(screen.getByRole('button', { name: 'Edit item' }))
}

function sectionOf(heading: RegExp) {
  return screen.getByRole('heading', { name: heading }).closest('section') as HTMLElement
}

it('moves an item to the freezer, then marks it as gone', async () => {
  let stock: InventoryItem[] = [PEAS]
  server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)),
    http.patch(`${API_URL}/inventory/item-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      const updated = { ...stock[0], ...body }
      stock = body.status === 'discarded' ? [] : [updated]
      return HttpResponse.json(updated)
    })
  )
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

  await waitFor(() => expect(within(sectionOf(/fridge/i)).getByText('Peas')).toBeInTheDocument())
  openEdit('Peas')
  fireEvent.click(screen.getByText('Freezer'))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))

  expect(await screen.findByText('Saved · Peas')).toBeInTheDocument()
  await waitFor(() =>
    expect(within(sectionOf(/freezer/i)).getByText('Peas')).toBeInTheDocument()
  )

  openEdit('Peas')
  fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

  expect(await screen.findByText('Marked as gone · Peas')).toBeInTheDocument()
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'More for Peas' })).not.toBeInTheDocument()
  )
})


it('brings a gone item back with the header Undo, not a toast that times out', async () => {
  // Undo used to live on the toast for eight seconds. The header's Undo is always there, says
  // what it will reverse, and does not depend on the sheet that raised the toast.
  const GONE = {
    batch_id: 'batch-peas',
    logged_at: '2026-09-22T08:00:00+00:00',
    steps: [
      {
        inventory_item_id: 'item-peas',
        product_name: 'Peas',
        unit: 'g',
        action: 'discard',
        quantity_consumed: 500,
      },
    ],
  }
  let stock: InventoryItem[] = [PEAS]
  let undoable: typeof GONE | null = null
  const undone: unknown[] = []
  server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(undoable)),
    http.patch(`${API_URL}/inventory/item-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      stock = []
      undoable = GONE
      return HttpResponse.json({ ...PEAS, ...body })
    }),
    http.post(`${API_URL}/inventory/undo`, async ({ request }) => {
      undone.push(await request.json())
      stock = [PEAS]
      undoable = null
      return HttpResponse.json({ undone: 1 })
    })
  )
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

  await waitFor(() => expect(screen.getByText('Peas')).toBeInTheDocument())
  openEdit('Peas')
  fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

  expect(await screen.findByText('Marked as gone · Peas')).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByText('Peas')).not.toBeInTheDocument())
  // The toast only says what happened; the way back is in the header
  expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()

  fireEvent.click(await screen.findByRole('button', { name: 'Undo Thrown away · Peas' }))

  await waitFor(() => expect(screen.getByText('Peas')).toBeInTheDocument())
  expect(undone).toEqual([{ batch_id: 'batch-peas' }])
})
