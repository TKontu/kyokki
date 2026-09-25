/**
 * ItemEditSheet: correct quantity, expiry and location, mark as gone, delete (MVP-S4).
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { ItemEditSheet } from '../ItemEditSheet'
import type { InventoryItem } from '@/types/inventory'

const OAT: InventoryItem = {
  id: 'item-oat',
  product_master_id: 'prod-oat',
  product_name: 'Oat drink',
  category: 'beverages',
  category_name: 'Beverages',
  category_icon: '🥤',
  receipt_id: null,
  initial_quantity: 10,
  current_quantity: 6,
  unit: 'dl',
  status: 'opened',
  purchase_date: '2026-09-10',
  expiry_date: '2026-09-30',
  expiry_source: 'calculated',
  opened_date: '2026-09-12',
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2026-09-10T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function mockApi({
  patchResponse = (body: Record<string, unknown>) =>
    HttpResponse.json({ ...OAT, ...body }),
}: { patchResponse?: (body: Record<string, unknown>) => Response } = {}) {
  const calls: { method: string; body?: Record<string, unknown> }[] = []
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([OAT])),
    http.patch(`${API_URL}/inventory/item-oat`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      calls.push({ method: 'PATCH', body })
      return patchResponse(body)
    }),
    http.delete(`${API_URL}/inventory/item-oat`, () => {
      calls.push({ method: 'DELETE' })
      return new HttpResponse(null, { status: 204 })
    })
  )
  return calls
}

function renderSheet(item: InventoryItem = OAT, onClose = jest.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const sheet = (current: InventoryItem) => (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ItemEditSheet item={current} open onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  const { rerender } = render(sheet(item))
  // What the 30s poll, a tap on a card or another device does to an open sheet
  moved = (next: Partial<InventoryItem>) => rerender(sheet({ ...item, ...next }))
  return onClose
}

let moved: (next: Partial<InventoryItem>) => void

function change(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

const save = () => screen.getByRole('button', { name: 'Save' })

describe('ItemEditSheet', () => {
  it('is prefilled from the item and Save waits for a change', () => {
    mockApi()
    renderSheet()

    expect(screen.getByRole('heading', { name: 'Oat drink' })).toBeInTheDocument()
    // Presence, not amounts (V2): there is no quantity to correct
    expect(screen.queryByLabelText(/Quantity/)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Expiry')).toHaveValue('2026-09-30')
    expect(screen.getByRole('radio', { name: 'Fridge' })).toBeChecked()
    expect(save()).toBeDisabled()
  })

  it('saves only the changed location', async () => {
    const calls = mockApi()
    const onClose = renderSheet()

    fireEvent.click(screen.getByText('Freezer'))
    fireEvent.click(save())

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(calls).toEqual([{ method: 'PATCH', body: { location: 'freezer' } }])
    expect(await screen.findByText('Saved · Oat drink')).toBeInTheDocument()
  })

  it('saves expiry and location together', async () => {
    const calls = mockApi()
    renderSheet()

    change('Expiry', '2026-10-15')
    fireEvent.click(screen.getByText('Pantry'))
    fireEvent.click(save())

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ expiry_date: '2026-10-15', location: 'pantry' })
  })

  it('marks the item as gone', async () => {
    const calls = mockApi()
    const onClose = renderSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(calls).toEqual([{ method: 'PATCH', body: { status: 'discarded' } }])
    expect(await screen.findByText('Marked as gone · Oat drink')).toBeInTheDocument()
    // The way back is the header's Undo now, not an eight-second button on the toast
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
  })

  it('offers Put it back instead, for an item already gone', () => {
    mockApi()
    renderSheet({ ...OAT, status: 'discarded' })

    expect(screen.queryByRole('button', { name: 'Mark as gone' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Put it back' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('puts a gone item back', async () => {
    const calls = mockApi()
    const onClose = renderSheet({ ...OAT, status: 'discarded' })

    fireEvent.click(screen.getByRole('button', { name: 'Put it back' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    // The status sent is only a signal: the server classifies the event from it, drops it, and
    // derives the result. It never comes back `sealed`.
    expect(calls).toEqual([{ method: 'PATCH', body: { status: 'opened' } }])
    expect(await screen.findByText('Back in the kitchen · Oat drink')).toBeInTheDocument()
  })

  it('asks before deleting and can go back', () => {
    const calls = mockApi()
    renderSheet()

    change('Expiry', '2026-10-04')
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(
      screen.getByText(
        'Delete Oat drink? This removes the item; what it wasted stays on Gone. Use Mark as gone if it was thrown away.'
      )
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.getByLabelText('Expiry')).toHaveValue('2026-10-04')
    expect(calls).toHaveLength(0)
  })

  it('deletes after confirmation', async () => {
    const calls = mockApi()
    const onClose = renderSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(screen.getByRole('button', { name: 'Yes, delete' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(calls).toEqual([{ method: 'DELETE' }])
    expect(await screen.findByText('Deleted · Oat drink')).toBeInTheDocument()
  })

  // A location outside the three known ones left every radio unchecked, so the sheet looked
  // like it had no answer and the diff against the item never produced a change (H04).
  it('offers a location it does not know as its own checked option', async () => {
    mockApi()
    renderSheet({ ...OAT, location: 'cellar' })

    expect(screen.getByRole('radio', { name: 'cellar' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Fridge' })).not.toBeChecked()
  })

  it('sends the move when the cook picks a known location instead', async () => {
    const calls = mockApi()
    renderSheet({ ...OAT, location: 'cellar' })

    fireEvent.click(screen.getByRole('radio', { name: 'Pantry' }))
    fireEvent.click(save())

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ location: 'pantry' })
  })

  it('keeps the sheet open with an API error message', async () => {
    mockApi({
      patchResponse: () =>
        HttpResponse.json({ detail: 'Inventory item not found' }, { status: 404 }),
    })
    const onClose = renderSheet()

    change('Expiry', '2026-10-03')
    fireEvent.click(save())

    expect(await screen.findByText('Inventory item not found')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Expiry')).toHaveValue('2026-10-03')
  })

  it('shows a friendly message when the server fails', async () => {
    mockApi({ patchResponse: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderSheet()

    fireEvent.click(screen.getByText('Pantry'))
    fireEvent.click(save())

    expect(await screen.findByText('Could not save Oat drink')).toBeInTheDocument()
  })
})

describe('while the item moves underneath the sheet (H25)', () => {
  // It used to seed the inputs at mount and diff them against the live item, so a background
  // change armed Save by itself and one press wrote the stale snapshot back over the server.

  it('shows what the server now says, for a field nobody has touched', () => {
    mockApi()
    renderSheet()

    moved({ expiry_date: '2026-10-02' })

    expect(screen.getByLabelText('Expiry')).toHaveValue('2026-10-02')
    expect(save()).toBeDisabled()
  })

  it('does not arm Save by itself', () => {
    mockApi()
    renderSheet()

    moved({ expiry_date: '2026-10-02', location: 'freezer' })

    expect(save()).toBeDisabled()
  })

  it('sends only the field the cook touched, not the one that moved', async () => {
    // The bug: editing the expiry while another device changed the item also sent the old
    // value of what changed - it used to resurrect a consumed helping as a correction.
    const calls = mockApi()
    renderSheet()

    change('Expiry', '2026-10-15')
    moved({ location: 'freezer' })
    fireEvent.click(save())

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ expiry_date: '2026-10-15' })
  })

  it('says so when a field the cook is editing moved as well', () => {
    mockApi()
    renderSheet()

    fireEvent.click(screen.getByText('Pantry'))
    moved({ location: 'freezer' })

    expect(screen.getByRole('status')).toHaveTextContent('Location changed to freezer while this was open')
  })

  it('keeps the cook\'s value when they say so, and still saves only that', async () => {
    const calls = mockApi()
    renderSheet()
    change('Expiry', '2026-10-15')
    moved({ expiry_date: '2026-10-02' })

    fireEvent.click(screen.getByRole('button', { name: 'Keep mine' }))
    fireEvent.click(save())

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ expiry_date: '2026-10-15' })
  })

  it('takes the new value when they say so, and then has nothing to save', () => {
    mockApi()
    renderSheet()
    change('Expiry', '2026-10-15')
    moved({ expiry_date: '2026-10-02' })

    fireEvent.click(screen.getByRole('button', { name: 'Use 2026-10-02' }))

    expect(screen.getByLabelText('Expiry')).toHaveValue('2026-10-02')
    expect(save()).toBeDisabled()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('says so about the expiry too', () => {
    mockApi()
    renderSheet()

    change('Expiry', '2026-10-15')
    moved({ expiry_date: '2026-10-02' })

    expect(screen.getByRole('status')).toHaveTextContent(
      'Expiry changed to 2026-10-02 while this was open'
    )
  })
})
