/**
 * ItemEditSheet: correct expiry and location, mark as gone, delete (MVP-S4), and reach the
 * product's own details - its category among them - from the item (Q25).
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { ItemEditSheet } from '../ItemEditSheet'
import type { InventoryItem } from '@/types/inventory'
import type { ProductMaster } from '@/types/product'

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
  beforeEach(() => window.localStorage.clear())

  it('shows the Finnish name once the cook has chosen Suomi (Post-MVP frontier item 13)', () => {
    window.localStorage.setItem('kyokki.language', 'fi')
    mockApi()
    renderSheet({ ...OAT, product_display_names: { fi: 'Kaurajuoma' } })

    expect(screen.getByRole('heading', { name: 'Kaurajuoma' })).toBeInTheDocument()
  })

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

describe('ItemEditSheet: where the item came from (Q26)', () => {
  const FROM_RECEIPT: InventoryItem = { ...OAT, receipt_id: 'receipt-1' }

  it('shows nothing, and asks nothing, for a hand-added item', () => {
    // onUnhandledRequest: 'error' fails the test if this reaches the API at all
    mockApi()
    renderSheet(OAT)

    expect(screen.queryByText(/^From /)).not.toBeInTheDocument()
  })

  it('names the receipt and the printed line, linking to the receipt', async () => {
    mockApi()
    server.use(
      http.get(`${API_URL}/inventory/item-oat/source`, () =>
        HttpResponse.json({
          receipt_id: 'receipt-1',
          store_chain: 's-group',
          purchase_date: '2026-09-26',
          line_text: 'KOKKIKARTANO KERMAINEN LOHIKEITTO',
          line_index: 1,
        })
      )
    )
    renderSheet(FROM_RECEIPT)

    const link = await screen.findByRole('link', {
      name: 'From S-group, 26.9.2026: KOKKIKARTANO KERMAINEN LOHIKEITTO',
    })
    expect(link).toHaveAttribute('href', '/receipts/receipt-1')
  })

  it('names only the receipt when the line is unknown (a legacy confirm)', async () => {
    mockApi()
    server.use(
      http.get(`${API_URL}/inventory/item-oat/source`, () =>
        HttpResponse.json({
          receipt_id: 'receipt-1',
          store_chain: 's-group',
          purchase_date: '2026-09-26',
          line_text: null,
          line_index: null,
        })
      )
    )
    renderSheet(FROM_RECEIPT)

    expect(
      await screen.findByRole('link', { name: 'From S-group, 26.9.2026' })
    ).toBeInTheDocument()
  })

  it('shows nothing when the item has a receipt but no source comes back', async () => {
    mockApi()
    server.use(
      http.get(`${API_URL}/inventory/item-oat/source`, () => HttpResponse.json(null))
    )
    renderSheet(FROM_RECEIPT)

    await waitFor(() => expect(screen.getByLabelText('Expiry')).toBeInTheDocument())
    expect(screen.queryByText(/^From /)).not.toBeInTheDocument()
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

const OAT_PRODUCT: ProductMaster = {
  id: 'prod-oat',
  canonical_name: 'Oat drink',
  category: 'beverages',
  storage_type: 'refrigerator',
  default_shelf_life_days: 14,
  opened_shelf_life_days: 5,
  frozen_shelf_life_days: null,
  avg_piece_grams: null,
  pack_grams: null,
  shelf_life_source: 'category',
  unit_type: 'volume',
  default_unit: 'dl',
  default_quantity: 10,
  min_stock_quantity: null,
  reorder_quantity: null,
  off_product_id: null,
  off_data: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

describe('ItemEditSheet: the product behind the item (Q25)', () => {
  function mockProduct() {
    const fetched: string[] = []
    server.use(
      http.get(`${API_URL}/products/prod-oat`, () => {
        fetched.push('prod-oat')
        return HttpResponse.json(OAT_PRODUCT)
      }),
      http.get(`${API_URL}/products/prod-oat/names`, () =>
        HttpResponse.json({ names: [], printed: [] })
      ),
      http.get(`${API_URL}/categories`, () => HttpResponse.json([]))
    )
    return fetched
  }

  it('shows the category the item is filed under', () => {
    mockApi()
    renderSheet()

    expect(screen.getByText('Category: Beverages')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change…' })).toBeInTheDocument()
  })

  it.each([['Change…'], ['Change product details…']])(
    'opens the product sheet from "%s"',
    async (button) => {
      mockApi()
      const fetched = mockProduct()
      renderSheet()

      fireEvent.click(screen.getByRole('button', { name: button }))

      expect(
        await screen.findByRole('heading', { name: 'Edit Oat drink' })
      ).toBeInTheDocument()
      expect(fetched).toEqual(['prod-oat'])
      // The item's own sheet has made way for the product's
      expect(screen.queryByRole('button', { name: 'Mark as gone' })).not.toBeInTheDocument()
    }
  )

  it('gives both ways to the product sheet a full touch target', () => {
    mockApi()
    renderSheet()

    // 44 px (`min-h-touch`), not the 36 px of a small button
    for (const name of ['Change…', 'Change product details…']) {
      expect(screen.getByRole('button', { name })).toHaveClass('min-h-touch')
    }
  })

  it('says "No category" rather than an id when the item has no category name', () => {
    mockApi()
    renderSheet({ ...OAT, category_name: '' })

    expect(screen.getByText('Category: No category')).toBeInTheDocument()
    expect(screen.queryByText(/beverages/)).not.toBeInTheDocument()
  })

  it('says it is loading the product rather than showing nothing', async () => {
    mockApi()
    let release: () => void = () => {}
    const released = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.get(`${API_URL}/products/prod-oat`, async () => {
        await released
        return HttpResponse.json(OAT_PRODUCT)
      }),
      http.get(`${API_URL}/products/prod-oat/names`, () =>
        HttpResponse.json({ names: [], printed: [] })
      ),
      http.get(`${API_URL}/categories`, () => HttpResponse.json([]))
    )
    renderSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Change…' }))

    expect(await screen.findByText('Loading product details…')).toBeInTheDocument()
    release()
    expect(await screen.findByRole('heading', { name: 'Edit Oat drink' })).toBeInTheDocument()
  })

  it('says so when the product cannot be loaded, and leads back to the item', async () => {
    mockApi()
    server.use(
      http.get(`${API_URL}/products/prod-oat`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 })
      )
    )
    renderSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Change…' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the product details for Oat drink.'
    )
    fireEvent.click(screen.getByRole('button', { name: 'Back to Oat drink' }))
    expect(screen.getByRole('button', { name: 'Mark as gone' })).toBeInTheDocument()
    expect(screen.getByText('Category: Beverages')).toBeInTheDocument()
  })

  it('holds both Change buttons while a save is in flight', async () => {
    let releasePatch: () => void = () => {}
    const patched = new Promise<void>((resolve) => {
      releasePatch = resolve
    })
    mockApi()
    // The save stays in flight until the test lets it land
    server.use(
      http.patch(`${API_URL}/inventory/item-oat`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        await patched
        return HttpResponse.json({ ...OAT, ...body })
      })
    )
    // A landed save refreshes the header's Undo
    server.use(http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)))
    const onClose = renderSheet()

    fireEvent.click(screen.getByText('Freezer'))
    fireEvent.click(save())

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Change…' })).toBeDisabled()
    )
    expect(screen.getByRole('button', { name: 'Change product details…' })).toBeDisabled()
    releasePatch()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Change…' })).toBeEnabled()
  })
})
