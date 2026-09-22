/**
 * QuickAddSheet: find or create a generic product, then add stock in one call (MVP-S3).
 */

import React from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useProducts'
import { QuickAddSheet } from '../QuickAddSheet'
import { addDaysISO } from '@/lib/dates'
import type { Category } from '@/types/category'
import type { InventoryItem } from '@/types/inventory'
import type { ProductMaster } from '@/types/product'

const CATEGORIES: Category[] = [
  {
    id: 'dairy',
    display_name: 'Dairy & Eggs',
    icon: '🥛',
    default_shelf_life_days: 7,
    sort_order: 20,
    default_storage: 'refrigerator',
  },
  {
    id: 'meat',
    display_name: 'Meat & Poultry',
    icon: '🥩',
    default_shelf_life_days: 5,
    sort_order: 10,
    default_storage: 'refrigerator',
  },
  {
    id: 'frozen',
    display_name: 'Frozen',
    icon: '🧊',
    default_shelf_life_days: 180,
    sort_order: 30,
    default_storage: 'freezer',
  },
]

const MILK: ProductMaster = {
  id: 'prod-milk',
  canonical_name: 'Milk',
  category: 'dairy',
  storage_type: 'refrigerator',
  default_shelf_life_days: 10,
  opened_shelf_life_days: null,
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
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
}

function created(overrides: Partial<InventoryItem> = {}): InventoryItem {
  return {
    id: 'item-new',
    product_master_id: 'prod-milk',
    product_name: 'Milk',
    category: 'dairy',
    category_name: 'Dairy & Eggs',
    category_icon: '🥛',
    receipt_id: null,
    initial_quantity: 10,
    current_quantity: 10,
    unit: 'dl',
    status: 'sealed',
    purchase_date: '2026-09-14',
    expiry_date: '2026-09-24',
    expiry_source: 'calculated',
    opened_date: null,
    batch_number: null,
    location: 'main_fridge',
    notes: null,
    created_at: '2026-09-14T10:00:00Z',
    consumed_at: null,
    ...overrides,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  jest.useRealTimers()
})
afterAll(() => server.close())

function mockApi({
  products = [MILK],
  addResponse = () => HttpResponse.json(created(), { status: 201 }),
}: {
  products?: ProductMaster[]
  addResponse?: () => Response
} = {}) {
  const bodies: Record<string, unknown>[] = []
  server.use(
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
    http.get(`${API_URL}/products`, ({ request }) => {
      const search = (new URL(request.url).searchParams.get('search') ?? '').toLowerCase()
      return HttpResponse.json(
        products.filter((p) => p.canonical_name.toLowerCase().includes(search))
      )
    }),
    http.post(`${API_URL}/inventory/quick-add`, async ({ request }) => {
      bodies.push((await request.json()) as Record<string, unknown>)
      return addResponse()
    })
  )
  return bodies
}

function renderSheet(onClose = jest.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <QuickAddSheet open onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  return onClose
}

function type(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}

/**
 * Type a search term and step over the debounce with fake timers, so the request is already in
 * flight when the assertion below starts waiting.
 *
 * Every search here used to spend 250 ms of wall clock inside a 1000 ms findBy budget, which is
 * a race the moment jest runs several suites next to a build. Real timers come straight back so
 * msw and findBy* work normally; only the debounce is skipped (H06).
 */
function search(term: string) {
  jest.useFakeTimers()
  type('Product', term)
  act(() => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
  })
  jest.useRealTimers()
}

function addButton() {
  return screen.getByRole('button', { name: /^add$/i })
}

describe('QuickAddSheet', () => {
  it('adds an existing product with its defaults', async () => {
    const bodies = mockApi()
    const onClose = renderSheet()

    search('mil')
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))

    expect(screen.getByLabelText('Quantity')).toHaveValue(10)
    expect(screen.getByRole('radio', { name: 'dl' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Fridge' })).toBeChecked()
    expect(screen.getByLabelText('Expiry')).toHaveValue(addDaysISO(10))

    fireEvent.click(addButton())

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(bodies).toEqual([
      { product_id: 'prod-milk', quantity: 10, unit: 'dl', location: 'main_fridge' },
    ])
    expect(await screen.findByText('Added 10 dl · Milk')).toBeInTheDocument()
  })

  it('creates a new product in a chosen category', async () => {
    const bodies = mockApi({
      products: [],
      addResponse: () =>
        HttpResponse.json(
          created({ product_name: 'Peas', unit: 'g', current_quantity: 500, location: 'freezer' }),
          { status: 201 }
        ),
    })
    renderSheet()

    search('Peas')
    fireEvent.click(await screen.findByRole('button', { name: 'Create new: Peas' }))

    expect(screen.getByText('New product')).toBeInTheDocument()
    expect(addButton()).toBeDisabled()

    fireEvent.click(await screen.findByRole('radio', { name: /frozen/i }))
    expect(screen.getByRole('radio', { name: 'Freezer' })).toBeChecked()
    expect(screen.getByLabelText('Expiry')).toHaveValue(addDaysISO(180))

    type('Quantity', '500')
    fireEvent.click(screen.getByRole('radio', { name: 'g' }))
    fireEvent.click(addButton())

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toEqual({
      name: 'Peas',
      category: 'frozen',
      quantity: 500,
      unit: 'g',
      location: 'freezer',
    })
    expect(await screen.findByText('Added 500 g · Peas')).toBeInTheDocument()
  })

  it('lists categories in their sort order', async () => {
    mockApi({ products: [] })
    renderSheet()

    search('Tofu')
    fireEvent.click(await screen.findByRole('button', { name: 'Create new: Tofu' }))

    const group = await screen.findByRole('radiogroup', { name: 'Category' })
    await waitFor(() => expect(within(group).getAllByRole('radio')).toHaveLength(3))
    expect(within(group).getAllByRole('radio').map((r) => r.closest('label')?.textContent)).toEqual([
      '🥩 Meat & Poultry',
      '🥛 Dairy & Eggs',
      '🧊 Frozen',
    ])
  })

  it('hides "Create new" when a product has exactly that name', async () => {
    mockApi()
    renderSheet()

    search('MILK')

    expect(await screen.findByRole('button', { name: 'Milk' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /create new/i })).not.toBeInTheDocument()
  })

  it.each(['0', '', '-2'])('rejects quantity %p', async (value) => {
    const bodies = mockApi()
    renderSheet()

    search('milk')
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))
    type('Quantity', value)

    expect(screen.getByText('Enter a quantity above 0')).toBeInTheDocument()
    expect(addButton()).toBeDisabled()
    fireEvent.click(addButton())
    expect(bodies).toHaveLength(0)
  })

  it('sends the expiry date only when it was changed', async () => {
    const bodies = mockApi()
    renderSheet()

    search('milk')
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))
    type('Expiry', '2026-12-24')
    fireEvent.click(addButton())

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ expiry_date: '2026-12-24' })
  })

  it('keeps the sheet open with an API error message', async () => {
    mockApi({
      addResponse: () =>
        HttpResponse.json({ detail: "Category required for new product 'Milk'" }, { status: 400 }),
    })
    const onClose = renderSheet()

    search('milk')
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))
    type('Quantity', '3')
    fireEvent.click(addButton())

    expect(
      await screen.findByText("Category required for new product 'Milk'")
    ).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Quantity')).toHaveValue(3)
  })

  it('shows a friendly message when the server fails', async () => {
    mockApi({ addResponse: () => HttpResponse.json({ detail: 'boom' }, { status: 500 }) })
    renderSheet()

    search('milk')
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))
    fireEvent.click(addButton())

    expect(await screen.findByText('Could not add Milk')).toBeInTheDocument()
  })

  // STORAGE_LOCATION[product.storage_type] used to be `undefined` for a storage type this build
  // does not know: no radio was checked and submit() posted `location: undefined` (H04).
  it('keeps a storage type it does not know as the location, checked and sent', async () => {
    const bodies = mockApi({
      products: [{ ...MILK, canonical_name: 'Kimchi', storage_type: 'cellar' as never }],
    })
    renderSheet()

    search('kim')
    fireEvent.click(await screen.findByRole('button', { name: 'Kimchi' }))

    expect(screen.getByRole('radio', { name: 'cellar' })).toBeChecked()

    fireEvent.click(addButton())
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ location: 'cellar' })
  })

  it('still lets the cook move it to a location it does know', async () => {
    const bodies = mockApi({
      products: [{ ...MILK, canonical_name: 'Kimchi', storage_type: 'cellar' as never }],
    })
    renderSheet()

    search('kim')
    fireEvent.click(await screen.findByRole('button', { name: 'Kimchi' }))
    fireEvent.click(screen.getByRole('radio', { name: 'Fridge' }))
    fireEvent.click(addButton())

    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0]).toMatchObject({ location: 'main_fridge' })
  })

  it('goes back to the search', async () => {
    mockApi()
    renderSheet()

    search('milk')
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))
    fireEvent.click(screen.getByRole('button', { name: /back/i }))

    expect(screen.getByLabelText('Product')).toHaveValue('milk')
  })
})
