/**
 * Correcting a product (H18).
 *
 * A product's shelf life, piece weight and unit are learned from the first receipt
 * that created it. Until this sheet there was no way to fix any of them, so a wrong
 * first guess was permanent: mince guessed at 5 days marks every future pack expired
 * on day six.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import ProductEditSheet from '../ProductEditSheet'
import type { Category } from '@/types/category'
import type { ProductMaster, ProductNames } from '@/types/product'

const CATEGORIES: Category[] = [
  {
    id: 'meat',
    display_name: 'Meat',
    icon: '🥩',
    default_shelf_life_days: 5,
    frozen_shelf_life_days: 180,
    sort_order: 1,
    default_storage: 'refrigerator',
  },
  {
    id: 'fish',
    display_name: 'Fish',
    icon: '🐟',
    default_shelf_life_days: 3,
    frozen_shelf_life_days: 120,
    sort_order: 2,
    default_storage: 'refrigerator',
  },
]

const NAMES: ProductNames = {
  names: [
    { id: 'n-own', name: 'ground beef', source: 'canonical', removable: false },
    { id: 'n-cook', name: 'jauheliha', source: 'cook', removable: true },
    { id: 'n-guess', name: 'minced pork', source: 'model', removable: true },
  ],
  printed: [
    {
      id: 'a-1',
      store_chain: 's-market',
      receipt_name: 'NAUDAN JAUHELIHA 400G',
      source: 'model',
      verified: false,
      occurrence_count: 2,
      last_seen: '2026-09-20T10:00:00Z',
    },
  ],
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  server.use(
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
    http.get(`${API_URL}/products/p-1/names`, () => HttpResponse.json(NAMES))
  )
})
afterEach(() => {
  server.resetHandlers()
  jest.useRealTimers()
})
afterAll(() => server.close())

const PRODUCT: ProductMaster = {
  id: 'p-1',
  canonical_name: 'Ground beef',
  category: 'meat',
  storage_type: 'refrigerator',
  default_shelf_life_days: 5,
  opened_shelf_life_days: null,
  frozen_shelf_life_days: null,
  avg_piece_grams: null,
  pack_grams: null,
  shelf_life_source: 'category',
  unit_type: 'weight',
  default_unit: 'g',
  default_quantity: 400,
  min_stock_quantity: null,
  reorder_quantity: null,
  off_product_id: null,
  off_data: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

function mockApi(response?: () => Response) {
  const patches: Record<string, unknown>[] = []
  server.use(
    http.patch(`${API_URL}/products/p-1`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patches.push(body)
      return response?.() ?? HttpResponse.json({ ...PRODUCT, ...body })
    })
  )
  return patches
}

function renderSheet(product: ProductMaster = PRODUCT, onClose = jest.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const sheet = (current: ProductMaster) => (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ProductEditSheet product={current} onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  const { rerender } = render(sheet(product))
  // What a refetch, or another cook, does to an open sheet
  moved = (next: Partial<ProductMaster>) => rerender(sheet({ ...product, ...next }))
  return onClose
}

let moved: (next: Partial<ProductMaster>) => void

const save = () => screen.getByRole('button', { name: 'Save' })

describe('ProductEditSheet', () => {
  it('prefills from the product', () => {
    renderSheet()

    expect(screen.getByLabelText('Name')).toHaveValue('Ground beef')
    expect(screen.getByLabelText('Keeps for')).toHaveValue(5)
    expect(screen.getByLabelText('Once opened')).toHaveValue(null)
  })

  it('sends only what changed', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('Keeps for'), { target: { value: '3' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ default_shelf_life_days: 3 })
  })

  it('cannot be saved until something changes', () => {
    renderSheet()

    expect(save()).toBeDisabled()
  })

  it('clears a value the cook empties', async () => {
    const patches = mockApi()
    renderSheet({ ...PRODUCT, opened_shelf_life_days: 3 })

    fireEvent.change(screen.getByLabelText('Once opened'), { target: { value: '' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ opened_shelf_life_days: null })
  })

  it('refuses a shelf life that is not a positive number', () => {
    renderSheet()

    fireEvent.change(screen.getByLabelText('Keeps for'), { target: { value: '0' } })

    // Every expiry date comes from this field, so it may not be blank or zero.
    expect(save()).toBeDisabled()
  })

  it('sends the unit without a unit type', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.click(screen.getByRole('radio', { name: 'pcs' }))
    fireEvent.change(screen.getByLabelText('One piece'), { target: { value: '110' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    // unit_type is derived server-side from default_unit; sending it would fight that.
    expect(patches[0]).toEqual({ default_unit: 'pcs', avg_piece_grams: 110 })
    expect(patches[0]).not.toHaveProperty('unit_type')
  })

  it('remembers what one pack weighs', async () => {
    // Q8: the receipt prints `1 pcs` of mince and never says 400 g, so the cook says it
    // once here and every later receipt from any shop stores grams.
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('One pack'), { target: { value: '400' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ pack_grams: 400 })
  })

  it('clears a pack weight that was wrong', async () => {
    const patches = mockApi()
    renderSheet({ ...PRODUCT, pack_grams: 400 })

    expect(screen.getByLabelText('One pack')).toHaveValue(400)
    fireEvent.change(screen.getByLabelText('One pack'), { target: { value: '' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ pack_grams: null })
  })

  it('closes on success', async () => {
    mockApi()
    const onClose = renderSheet()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Minced beef' } })
    fireEvent.click(save())

    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('keeps the sheet open and shows the reason when the API refuses', async () => {
    mockApi(() =>
      HttpResponse.json({ detail: 'Record already exists.' }, { status: 409 })
    )
    const onClose = renderSheet()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Milk' } })
    fireEvent.click(save())

    expect(await screen.findByText('Record already exists.')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('while the product moves underneath the sheet (H25)', () => {
  it('follows the server for a field nobody has touched', () => {
    renderSheet()

    moved({ default_shelf_life_days: 9 })

    expect(screen.getByLabelText('Keeps for')).toHaveValue(9)
    expect(save()).toBeDisabled()
  })

  it('does not arm Save by itself', () => {
    renderSheet()

    moved({ canonical_name: 'Minced beef', default_shelf_life_days: 9 })

    expect(save()).toBeDisabled()
  })

  it('sends only the field the cook touched', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Minced beef' } })
    moved({ default_shelf_life_days: 9 })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ canonical_name: 'Minced beef' })
  })

  it('says so when a field the cook is editing moved as well', () => {
    renderSheet()

    fireEvent.change(screen.getByLabelText('Keeps for'), { target: { value: '3' } })
    moved({ default_shelf_life_days: 9 })

    expect(screen.getByRole('status')).toHaveTextContent(
      'Keeps for changed to 9 while this was open'
    )
  })
})

describe('category and frozen life (H52)', () => {
  it('moves the product to another category', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.click(await screen.findByRole('radio', { name: /Fish/ }))
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ category: 'fish' })
  })

  it('says a placeholder shelf life follows the category', async () => {
    renderSheet()

    expect(await screen.findByText(/follows the category/)).toBeInTheDocument()
  })

  it('does not say so once the cook has set the shelf life', async () => {
    renderSheet({ ...PRODUCT, shelf_life_source: 'cook' })

    await screen.findByRole('radio', { name: /Fish/ })
    expect(screen.queryByText(/follows the category/)).not.toBeInTheDocument()
  })

  it("shows the category's frozen life when the product has none", async () => {
    renderSheet()

    expect(await screen.findByPlaceholderText('180')).toBeInTheDocument()
    expect(screen.getByLabelText('Once frozen')).toHaveValue(null)
  })

  it('sets a frozen life of its own', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('Once frozen'), { target: { value: '30' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ frozen_shelf_life_days: 30 })
  })

  it('clearing it hands the frozen life back to the category', async () => {
    const patches = mockApi()
    renderSheet({ ...PRODUCT, frozen_shelf_life_days: 30 })

    fireEvent.change(screen.getByLabelText('Once frozen'), { target: { value: '' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ frozen_shelf_life_days: null })
  })

  it('says so when the category moved while the sheet was open', async () => {
    renderSheet()

    fireEvent.click(await screen.findByRole('radio', { name: /Fish/ }))
    moved({ category: 'dairy' })

    expect(screen.getByRole('status')).toHaveTextContent('Category changed')
  })
})

describe('matching names (H52)', () => {
  it('lists the names with whose word each is', async () => {
    renderSheet()

    const guess = await screen.findByText('minced pork')
    expect(guess.closest('li')).toHaveTextContent('auto')
    expect(screen.getByText('jauheliha').closest('li')).toHaveTextContent('yours')
    expect(screen.getByText('NAUDAN JAUHELIHA 400G').closest('li')).toHaveTextContent(
      's-market'
    )
  })

  it('offers no way to remove the product’s own name', async () => {
    renderSheet()

    await screen.findByText('ground beef')
    expect(
      screen.queryByRole('button', { name: 'Remove ground beef' })
    ).not.toBeInTheDocument()
  })

  it('removes a name on the second tap', async () => {
    const removed: string[] = []
    let names = NAMES
    server.use(
      http.get(`${API_URL}/products/p-1/names`, () => HttpResponse.json(names)),
      http.delete(`${API_URL}/products/p-1/names/:nameId`, ({ params }) => {
        removed.push(String(params.nameId))
        names = { ...names, names: names.names.filter((n) => n.id !== params.nameId) }
        return new HttpResponse(null, { status: 204 })
      })
    )
    renderSheet()

    const remove = await screen.findByRole('button', { name: 'Remove minced pork' })
    fireEvent.click(remove)
    expect(removed).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'Confirm remove minced pork' }))

    await waitFor(() => expect(removed).toEqual(['n-guess']))
    await waitFor(() => expect(screen.queryByText('minced pork')).not.toBeInTheDocument())
  })

  it('removes a printed name through its own route', async () => {
    const removed: string[] = []
    server.use(
      http.delete(`${API_URL}/products/p-1/aliases/:aliasId`, ({ params }) => {
        removed.push(String(params.aliasId))
        return new HttpResponse(null, { status: 204 })
      })
    )
    renderSheet()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Remove NAUDAN JAUHELIHA 400G' })
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Confirm remove NAUDAN JAUHELIHA 400G' })
    )

    await waitFor(() => expect(removed).toEqual(['a-1']))
  })
})
