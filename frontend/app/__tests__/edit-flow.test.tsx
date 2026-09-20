/**
 * End-to-end edit flow on the home page against msw-mocked endpoints (MVP-S4):
 * Edit -> move to the freezer -> Save -> list regroups; Edit -> Mark as gone -> item disappears.
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

function sectionOf(heading: RegExp) {
  return screen.getByRole('heading', { name: heading }).closest('section') as HTMLElement
}

it('moves an item to the freezer, then marks it as gone', async () => {
  let stock: InventoryItem[] = [PEAS]
  server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
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
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
  fireEvent.click(screen.getByText('Freezer'))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))

  expect(await screen.findByText('Saved · Peas')).toBeInTheDocument()
  await waitFor(() =>
    expect(within(sectionOf(/freezer/i)).getByText('Peas')).toBeInTheDocument()
  )

  fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
  fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

  expect(await screen.findByText('Marked as gone · Peas')).toBeInTheDocument()
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  )
})


it('puts an item back when Undo is tapped after the sheet has closed', async () => {
  // The bug this guards: `ItemEditSheet` closes itself on success, so by the time anyone taps
  // Undo the component - and its mutation observer - is gone. The restore therefore runs
  // through the query client and the API module, both of which outlive the sheet.
  let current: InventoryItem = PEAS
  let stock: InventoryItem[] = [PEAS]
  const patches: Partial<InventoryItem>[] = []
  server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.patch(`${API_URL}/inventory/item-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      patches.push(body)
      // What the server actually does with a restore: the status sent is only a signal, and
      // the result is derived. It never comes back `sealed` - it was in the bin (H23).
      const status = body.status === 'discarded' ? 'discarded' : 'opened'
      // The row outlives the list: a discarded item is hidden, not deleted, which is exactly
      // what makes restoring it possible.
      current = { ...current, ...body, status } as InventoryItem
      stock = status === 'discarded' ? [] : [current]
      return HttpResponse.json(current)
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
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
  fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

  // The sheet is gone by now, which is the whole point
  expect(await screen.findByText('Marked as gone · Peas')).toBeInTheDocument()
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  )

  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))

  expect(await screen.findByText('Back in the kitchen · Peas')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByText('Peas')).toBeInTheDocument())
  expect(patches.map((body) => body.status)).toEqual(['discarded', 'opened'])
})

it('leaves the item gone when the Undo is not taken', async () => {
  let stock: InventoryItem[] = [PEAS]
  server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.patch(`${API_URL}/inventory/item-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      stock = []
      return HttpResponse.json({ ...PEAS, ...body })
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
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
  fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

  expect(await screen.findByText('Marked as gone · Peas')).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByText('Peas')).not.toBeInTheDocument())
  // Offered, not taken: the item stays gone.
  expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument()
})
