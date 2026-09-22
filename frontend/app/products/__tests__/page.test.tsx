/**
 * The catalog (Q11).
 *
 * Two things this screen exists for: reaching a product that is not in stock, and saying
 * which shelf lives are guesses. Before it, `ProductEditSheet` was rendered from exactly
 * one place - an inventory item's edit sheet - so 35 of the homelab's 50 products could
 * not be opened at all.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import ProductsPage from '../page'
import type { CatalogEstimateResponse, ProductMaster } from '@/types/product'

const CATEGORIES = [
  {
    id: 'meat',
    display_name: 'Meat & Poultry',
    icon: '🥩',
    default_shelf_life_days: 5,
    sort_order: 10,
    default_storage: 'refrigerator',
  },
  {
    id: 'pantry',
    display_name: 'Pantry',
    icon: '🥫',
    default_shelf_life_days: 365,
    sort_order: 20,
    default_storage: 'pantry',
  },
]

function product(overrides: Partial<ProductMaster> = {}): ProductMaster {
  return {
    id: 'p-mince',
    canonical_name: 'Ground beef',
    category: 'meat',
    storage_type: 'refrigerator',
    default_shelf_life_days: 5,
    shelf_life_source: 'category',
    opened_shelf_life_days: null,
    avg_piece_grams: null,
    pack_grams: null,
    unit_type: 'weight',
    default_unit: 'g',
    default_quantity: 400,
    min_stock_quantity: null,
    reorder_quantity: null,
    off_product_id: null,
    off_data: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage(products: ProductMaster[], estimate?: CatalogEstimateResponse) {
  const calls: string[] = []
  server.use(
    http.get(`${API_URL}/products`, () => HttpResponse.json(products)),
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
    http.post(`${API_URL}/products/estimate`, ({ request }) => {
      calls.push(new URL(request.url).searchParams.get('apply') ?? 'false')
      return HttpResponse.json(
        estimate ?? {
          considered: 0,
          answered: 0,
          applied: false,
          items_redated: 0,
          changes: [],
        }
      )
    })
  )
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ProductsPage />
      </ToastProvider>
    </QueryClientProvider>
  )
  return calls
}

describe('ProductsPage', () => {
  it('lists every product, grouped by category', async () => {
    renderPage([product(), product({ id: 'p-pasta', canonical_name: 'Pasta', category: 'pantry' })])

    expect(await screen.findByText('Ground beef')).toBeInTheDocument()
    expect(screen.getByText('Pasta')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Meat & Poultry' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Pantry' })).toBeInTheDocument()
  })

  it('says which shelf lives are only the category default', async () => {
    // The one number on this screen a cook can act on, and the reason 46 of 50 were wrong.
    renderPage([
      product(),
      product({
        id: 'p-pasta',
        canonical_name: 'Pasta',
        category: 'pantry',
        default_shelf_life_days: 720,
        shelf_life_source: 'model',
      }),
      product({
        id: 'p-ham',
        canonical_name: 'Ham',
        default_shelf_life_days: 10,
        shelf_life_source: 'cook',
      }),
    ])

    expect(await screen.findByText(/5 days · from the category/)).toBeInTheDocument()
    expect(screen.getByText(/720 days · estimated/)).toBeInTheDocument()
    expect(screen.getByText(/10 days · you set this/)).toBeInTheDocument()
  })

  it('counts the guesses in the header', async () => {
    renderPage([product(), product({ id: 'p-ham', canonical_name: 'Ham' })])

    expect(await screen.findByText(/2 products, 2 still using a category default/)).toBeInTheDocument()
  })

  it('opens the editor for a product that is not in stock', async () => {
    // The whole point: ProductEditSheet used to be reachable only through an inventory item.
    renderPage([product()])

    fireEvent.click(await screen.findByRole('button', { name: /Ground beef/ }))

    expect(await screen.findByLabelText('Keeps for')).toHaveValue(5)
  })

  it('proposes before it writes, and only writes on a second tap', async () => {
    const calls = renderPage([product()], {
      considered: 1,
      answered: 1,
      applied: false,
      items_redated: 0,
      changes: [
        {
          id: 'p-mince',
          canonical_name: 'Ground beef',
          category: 'meat',
          current_days: 5,
          proposed_days: 2,
          current_opened: null,
          proposed_opened: null,
        },
      ],
    })

    fireEvent.click(await screen.findByRole('button', { name: /Estimate the guesses/ }))

    const proposal = await screen.findByRole('region', { name: /Proposed shelf lives/ })
    expect(within(proposal).getByText(/5 → 2 days/)).toBeInTheDocument()
    await waitFor(() => expect(calls).toEqual(['false']))

    fireEvent.click(within(proposal).getByRole('button', { name: /Save 1/ }))

    await waitFor(() => expect(calls).toEqual(['false', 'true']))
  })

  it('says what happened to the food, not just to the catalog (Q12)', async () => {
    // A corrected shelf life re-dates the stock that was dated by the old one. Saying
    // only "saved 1 shelf life" would hide the half the cook actually cares about.
    renderPage([product()], {
      considered: 1,
      answered: 1,
      applied: true,
      items_redated: 3,
      changes: [
        {
          id: 'p-mince',
          canonical_name: 'Ground beef',
          category: 'meat',
          current_days: 5,
          proposed_days: 2,
          current_opened: null,
          proposed_opened: null,
        },
      ],
    })

    fireEvent.click(await screen.findByRole('button', { name: /Estimate the guesses/ }))

    expect(await screen.findByText(/Saved 1 shelf lives, 3 items re-dated/)).toBeInTheDocument()
  })

  it('a proposal can be discarded without writing anything', async () => {
    const calls = renderPage([product()], {
      considered: 1,
      answered: 1,
      applied: false,
      items_redated: 0,
      changes: [
        {
          id: 'p-mince',
          canonical_name: 'Ground beef',
          category: 'meat',
          current_days: 5,
          proposed_days: 2,
          current_opened: null,
          proposed_opened: null,
        },
      ],
    })

    fireEvent.click(await screen.findByRole('button', { name: /Estimate the guesses/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Discard/ }))

    await waitFor(() =>
      expect(screen.queryByRole('region', { name: /Proposed shelf lives/ })).not.toBeInTheDocument()
    )
    expect(calls).toEqual(['false'])
  })

  it('says so when the model agreed with everything already stored', async () => {
    renderPage([product()], { considered: 1, answered: 1, applied: false, items_redated: 0, changes: [] })

    fireEvent.click(await screen.findByRole('button', { name: /Estimate the guesses/ }))

    expect(await screen.findByRole('status')).toHaveTextContent(/agreed with what is already stored/)
  })

  it('offers nothing to estimate when no product is guessing', async () => {
    renderPage([product({ shelf_life_source: 'cook' })])

    await screen.findByText('Ground beef')
    expect(screen.queryByRole('button', { name: /Estimate the guesses/ })).not.toBeInTheDocument()
  })

  it('points an empty catalog at where products come from', async () => {
    renderPage([])

    expect(await screen.findByText(/created when you confirm a receipt/)).toBeInTheDocument()
  })
})
