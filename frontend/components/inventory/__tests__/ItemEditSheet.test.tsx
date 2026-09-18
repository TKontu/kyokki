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
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ItemEditSheet item={item} open onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  return onClose
}

function change(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

const save = () => screen.getByRole('button', { name: 'Save' })

describe('ItemEditSheet', () => {
  it('is prefilled from the item and Save waits for a change', () => {
    mockApi()
    renderSheet()

    expect(screen.getByRole('heading', { name: 'Oat drink' })).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity (dl)')).toHaveValue(6)
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

  it('saves quantity and expiry together', async () => {
    const calls = mockApi()
    renderSheet()

    change('Quantity (dl)', '12')
    change('Expiry', '2026-10-15')
    fireEvent.click(save())

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ current_quantity: 12, expiry_date: '2026-10-15' })
  })

  it('explains what 0 and larger amounts do', () => {
    mockApi()
    renderSheet()

    expect(
      screen.getByText('0 marks it used up. More than 10 dl raises the full amount.')
    ).toBeInTheDocument()
  })

  it('allows 0', async () => {
    const calls = mockApi()
    renderSheet()

    change('Quantity (dl)', '0')
    fireEvent.click(save())

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ current_quantity: 0 })
  })

  it.each(['-1', ''])('rejects quantity %p', (value) => {
    const calls = mockApi()
    renderSheet()

    change('Quantity (dl)', value)

    expect(screen.getByText('Enter 0 or more')).toBeInTheDocument()
    expect(save()).toBeDisabled()
    expect(calls).toHaveLength(0)
  })

  it('marks the item as gone', async () => {
    const calls = mockApi()
    const onClose = renderSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Mark as gone' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(calls).toEqual([{ method: 'PATCH', body: { status: 'discarded' } }])
    expect(await screen.findByText('Marked as gone · Oat drink')).toBeInTheDocument()
  })

  it('does not offer Mark as gone for an item already gone', () => {
    mockApi()
    renderSheet({ ...OAT, status: 'discarded' })

    expect(screen.queryByRole('button', { name: 'Mark as gone' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('asks before deleting and can go back', () => {
    const calls = mockApi()
    renderSheet()

    change('Quantity (dl)', '4')
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    expect(
      screen.getByText(
        'Delete Oat drink? This removes the item and its history. Use Mark as gone if it was thrown away.'
      )
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.getByLabelText('Quantity (dl)')).toHaveValue(4)
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

    change('Quantity (dl)', '3')
    fireEvent.click(save())

    expect(await screen.findByText('Inventory item not found')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Quantity (dl)')).toHaveValue(3)
  })

  it('shows a friendly message when the server fails', async () => {
    mockApi({ patchResponse: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderSheet()

    fireEvent.click(screen.getByText('Pantry'))
    fireEvent.click(save())

    expect(await screen.findByText('Could not save Oat drink')).toBeInTheDocument()
  })
})
