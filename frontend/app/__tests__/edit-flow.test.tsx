/**
 * End-to-end edit flow against msw-mocked endpoints (MVP-S4), from an area's grid (V4), which
 * is where a fresh item's tile lives: … -> Edit item -> move to the freezer -> Save -> the tile
 * leaves the area; Mark as gone -> the tile disappears, and the header's Undo brings it back.
 */

import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import AreaPage from '../area/[id]/page'
import type { InventoryItem } from '@/types/inventory'

const PEAS: InventoryItem = {
  id: 'item-peas',
  product_master_id: 'prod-peas',
  product_name: 'Peas',
  category: 'produce',
  category_name: 'Produce',
  category_icon: '🫛',
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
  opened_shelf_life_days: null,
  avg_piece_grams: null,
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** Edit lives behind the tile's "…": a tap on the tile itself uses the item up. */
function openEdit(name: string) {
  fireEvent.click(screen.getByRole('button', { name: `More for ${name}` }))
  fireEvent.click(screen.getByRole('button', { name: 'Edit item' }))
}

const peasTile = () => screen.queryByRole('button', { name: 'Peas, keeps' })

function renderVeggies() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AreaPage params={{ id: 'veggies' }} />
      </ToastProvider>
    </QueryClientProvider>
  )
  return queryClient
}

it('moves an item to the freezer, and it leaves the area', async () => {
  let stock: InventoryItem[] = [PEAS]
  const patches: Partial<InventoryItem>[] = []
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)),
    http.patch(`${API_URL}/inventory/item-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      patches.push(body)
      stock = [{ ...stock[0], ...body }]
      return HttpResponse.json(stock[0])
    })
  )
  renderVeggies()

  await waitFor(() => expect(peasTile()).toBeInTheDocument())
  openEdit('Peas')
  fireEvent.click(screen.getByText('Freezer'))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))

  expect(await screen.findByText('Saved · Peas')).toBeInTheDocument()
  expect(patches).toEqual([{ location: 'freezer' }])
  // In the freezer it is the freezer's, whatever it is
  await waitFor(() => expect(peasTile()).not.toBeInTheDocument())
})

it('marks an item as gone', async () => {
  let stock: InventoryItem[] = [PEAS]
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)),
    http.patch(`${API_URL}/inventory/item-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      stock = []
      return HttpResponse.json({ ...PEAS, ...body })
    })
  )
  renderVeggies()

  await waitFor(() => expect(peasTile()).toBeInTheDocument())
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
  renderVeggies()

  await waitFor(() => expect(peasTile()).toBeInTheDocument())
  openEdit('Peas')
  fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

  expect(await screen.findByText('Marked as gone · Peas')).toBeInTheDocument()
  await waitFor(() => expect(peasTile()).not.toBeInTheDocument())
  // The toast only says what happened; the way back is in the header
  expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()

  fireEvent.click(await screen.findByRole('button', { name: 'Undo Thrown away · Peas' }))

  await waitFor(() => expect(peasTile()).toBeInTheDocument())
  expect(undone).toEqual([{ batch_id: 'batch-peas' }])
})

it('saves only what the cook changed when the item moves under the open sheet', async () => {
  // The H25 bug, end to end: a consume elsewhere while the edit sheet was open, then saving an
  // expiry, used to send the old quantity too - putting the helping back as a correction,
  // which the history then recorded as one.
  let stock: InventoryItem[] = [PEAS]
  const patches: Partial<InventoryItem>[] = []
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)),
    http.patch(`${API_URL}/inventory/item-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      patches.push(body)
      return HttpResponse.json({ ...stock[0], ...body })
    })
  )
  const queryClient = renderVeggies()
  await waitFor(() => expect(peasTile()).toBeInTheDocument())

  openEdit('Peas')
  fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: '2099-04-01' } })
  // Somebody eats a quarter of the peas on another screen while this sheet sits open
  stock = [{ ...PEAS, current_quantity: 375, status: 'partial' }]
  await act(() => queryClient.invalidateQueries({ queryKey: ['inventory'] }))
  await waitFor(() => expect(screen.getByLabelText('Quantity (g)')).toHaveValue(375))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))

  await waitFor(() => expect(patches).toHaveLength(1))
  expect(patches[0]).toEqual({ expiry_date: '2099-04-01' })
})
