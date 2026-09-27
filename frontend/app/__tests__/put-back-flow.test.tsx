/**
 * Putting back a grey "used today" tile, end to end (Q22): the tap on an area page sends the
 * item back to its full amount, the API logs that as a correction, and the header's Undo then
 * says what it would reverse in the cook's words - "Put back", not "Correction".
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import AreaPage from '../area/[id]/page'
import type { UndoPreview } from '@/types/consumption'
import type { InventoryItem } from '@/types/inventory'

function inDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

const POTATO: InventoryItem = {
  id: 'item-potato',
  product_master_id: 'p-potato',
  product_name: 'Potato',
  category: 'produce',
  category_name: 'Produce',
  category_icon: '🥔',
  receipt_id: null,
  initial_quantity: 6,
  current_quantity: 0,
  unit: 'pcs',
  status: 'empty',
  purchase_date: '2026-09-20',
  expiry_date: inDays(14),
  expiry_source: 'calculated',
  opened_date: null,
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2026-09-20T10:00:00Z',
  consumed_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
  opened_shelf_life_days: null,
  avg_piece_grams: null,
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

it('reads "Undo Put back · Potato" after a grey tile is tapped back', async () => {
  // A small stand-in for the API: the PATCH sets the item back and logs what the backend
  // logs for it - a `correct` step with the amount unsigned
  let potato = POTATO
  let undo: UndoPreview | null = null
  const patches: unknown[] = []
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([potato])),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(undo)),
    http.patch(`${API_URL}/inventory/item-potato`, async ({ request }) => {
      const body = (await request.json()) as { current_quantity: number }
      patches.push(body)
      potato = { ...potato, current_quantity: body.current_quantity, status: 'opened', consumed_at: null }
      undo = {
        batch_id: 'b-potato',
        logged_at: new Date().toISOString(),
        steps: [
          {
            inventory_item_id: 'item-potato',
            product_name: 'Potato',
            unit: 'pcs',
            action: 'correct',
            quantity_consumed: body.current_quantity,
          },
        ],
      }
      return HttpResponse.json(potato)
    })
  )
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

  fireEvent.click(await screen.findByRole('button', { name: 'Potato, used up' }))

  await waitFor(() => expect(patches).toEqual([{ current_quantity: 6 }]))
  expect(
    await screen.findByRole('button', { name: 'Undo Put back · Potato' })
  ).toBeEnabled()
})
