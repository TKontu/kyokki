/**
 * "This is not X" (CL8 L3): move wrongly joined items off a product, onto a new product or an
 * existing one, see what moved, and undo it. The API is mocked to the round's contract.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { SplitSheet } from '../SplitSheet'
import type { Category } from '@/types/category'
import type { ProductMaster, ProductSource, ProductSplitResponse } from '@/types/product'

const CATEGORIES: Category[] = [
  {
    id: 'ready_meals',
    display_name: 'Ready meals',
    icon: '🍲',
    default_shelf_life_days: 3,
    frozen_shelf_life_days: 90,
    sort_order: 1,
    default_storage: 'refrigerator',
    shelf_life_min_days: 1,
    shelf_life_max_days: 14,
  },
  {
    id: 'bakery',
    display_name: 'Bakery',
    icon: '🥐',
    default_shelf_life_days: 4,
    frozen_shelf_life_days: 90,
    sort_order: 2,
    default_storage: 'pantry',
    shelf_life_min_days: 1,
    shelf_life_max_days: 30,
  },
]

function product(id: string, name: string, category = 'bakery'): ProductMaster {
  return {
    id,
    canonical_name: name,
    category,
    storage_type: 'refrigerator',
    default_shelf_life_days: 3,
    opened_shelf_life_days: null,
    frozen_shelf_life_days: null,
    avg_piece_grams: null,
    pack_grams: null,
    shelf_life_source: 'model',
    unit_type: 'count',
    default_unit: 'pcs',
    default_quantity: null,
    min_stock_quantity: null,
    reorder_quantity: null,
    off_product_id: null,
    off_data: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  }
}

const PIES = product('p-1', 'Rice pies')
const KARELIAN_PIE = product('p-2', 'Karelian pie')
const STEW = product('p-new', 'Karelian stew', 'ready_meals')

const GROUP: ProductSource = {
  key: 'line:s-group:karjalanpaisti',
  label: 'KARJALANPAISTI',
  store_chain: 's-group',
  kind: 'receipt',
  item_ids: ['i-1', 'i-2', 'i-3'],
  active_count: 3,
  total_count: 4,
  first_seen: '2026-09-30',
  last_seen: '2026-10-06',
}

function splitResponse(overrides: Partial<ProductSplitResponse> = {}): ProductSplitResponse {
  return {
    reassignment_id: 'r-1',
    source_product: PIES,
    target_product: STEW,
    target_created: true,
    moved_item_ids: ['i-1', 'i-2', 'i-3'],
    moved_keys: [{ kind: 'alias', value: 'KARJALANPAISTI', store_chain: 's-group' }],
    source_shelf_life: { days: 3, source: 'model', observations_left: 2 },
    ...overrides,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  window.localStorage.clear()
  server.use(
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
    http.get(`${API_URL}/products`, ({ request }) => {
      const search = new URL(request.url).searchParams.get('search') ?? ''
      return HttpResponse.json(
        [PIES, KARELIAN_PIE].filter((p) =>
          p.canonical_name.toLowerCase().includes(search.toLowerCase())
        )
      )
    })
  )
})
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function mockSplit(responses: Array<() => Response> = [() => HttpResponse.json(splitResponse())]) {
  const bodies: unknown[] = []
  server.use(
    http.post(`${API_URL}/products/p-1/split`, async ({ request }) => {
      bodies.push(await request.json())
      const next = responses[Math.min(bodies.length - 1, responses.length - 1)]
      return next()
    })
  )
  return bodies
}

function renderSheet(
  props: Partial<React.ComponentProps<typeof SplitSheet>> = {}
): { onClose: jest.Mock; onDone: jest.Mock } {
  const onClose = jest.fn()
  const onDone = jest.fn()
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SplitSheet
          productId="p-1"
          productName="Rice pies"
          productCategory="bakery"
          itemIds={['i-1']}
          sourceGroup={GROUP}
          onClose={onClose}
          onDone={onDone}
          {...props}
        />
      </ToastProvider>
    </QueryClientProvider>
  )
  return { onClose, onDone }
}

const moveButton = () => screen.getByRole('button', { name: 'Move' })

async function typeNewName(name: string) {
  fireEvent.change(screen.getByLabelText('New product name'), { target: { value: name } })
  // The category defaults to the source product's once the categories load
  await waitFor(() => expect(screen.getByLabelText('Category')).toHaveValue('bakery'))
}

describe('SplitSheet', () => {
  it('moves the item and its group to a new product with the contract body', async () => {
    const bodies = mockSplit()
    const { onDone } = renderSheet()

    expect(screen.getByLabelText('New product name')).toHaveValue('')
    expect(
      screen.getByRole('checkbox', {
        name: 'Also move the 2 other items that came via KARJALANPAISTI (S-group)',
      })
    ).toBeChecked()
    expect(
      screen.getByText('Next receipts with KARJALANPAISTI go to the new product')
    ).toBeInTheDocument()
    expect(moveButton()).toBeDisabled()

    await typeNewName('Karelian stew')
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'ready_meals' } })
    fireEvent.click(moveButton())

    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(bodies).toEqual([
      {
        item_ids: ['i-1', 'i-2', 'i-3'],
        target: { new: { name: 'Karelian stew', category: 'ready_meals' } },
        move_keys: true,
      },
    ])
  })

  it('moves only the chosen item when the group toggle is off', async () => {
    const bodies = mockSplit()
    const { onDone } = renderSheet()

    await typeNewName('Karelian stew')
    fireEvent.click(screen.getByRole('checkbox', { name: /Also move the 2 other items/ }))
    fireEvent.click(moveButton())

    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(bodies).toEqual([
      {
        item_ids: ['i-1'],
        target: { new: { name: 'Karelian stew', category: 'bakery' } },
        move_keys: true,
      },
    ])
  })

  it('shows no group toggle when there is no group or nothing more in it', () => {
    mockSplit()
    renderSheet({ itemIds: GROUP.item_ids })
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('moves to an existing product picked with the product search', async () => {
    const bodies = mockSplit([
      () =>
        HttpResponse.json(splitResponse({ target_product: KARELIAN_PIE, target_created: false })),
    ])
    const { onDone } = renderSheet()

    fireEvent.click(screen.getByRole('radio', { name: 'Existing product' }))
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'pie' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Karelian pie' }))
    expect(screen.getByText('Moving to Karelian pie')).toBeInTheDocument()
    expect(
      screen.getByText('Next receipts with KARJALANPAISTI go to Karelian pie')
    ).toBeInTheDocument()
    fireEvent.click(moveButton())

    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(bodies).toEqual([
      { item_ids: ['i-1', 'i-2', 'i-3'], target: { product_id: 'p-2' }, move_keys: true },
    ])
    expect(await screen.findByText('Moved 3 items to Karelian pie')).toBeInTheDocument()
  })

  it('will not move a product onto itself', async () => {
    mockSplit()
    renderSheet()

    fireEvent.click(screen.getByRole('radio', { name: 'Existing product' }))
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'rice' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Rice pies' }))

    expect(
      screen.getByText('That is Rice pies itself — pick another product.')
    ).toBeInTheDocument()
    expect(moveButton()).toBeDisabled()
  })

  it('offers the existing product on 409 name_exists and moves to it', async () => {
    const bodies = mockSplit([
      () =>
        HttpResponse.json(
          { detail: { code: 'name_exists', product_id: 'p-2', name: 'Karelian pie' } },
          { status: 409 }
        ),
      () =>
        HttpResponse.json(splitResponse({ target_product: KARELIAN_PIE, target_created: false })),
    ])
    const { onDone } = renderSheet()

    await typeNewName('karelian pie')
    fireEvent.click(moveButton())

    expect(
      await screen.findByText('Karelian pie already exists. Move to it instead?')
    ).toBeInTheDocument()
    expect(onDone).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Move to Karelian pie' }))

    await waitFor(() => expect(onDone).toHaveBeenCalled())
    expect(bodies[1]).toEqual({
      item_ids: ['i-1', 'i-2', 'i-3'],
      target: { product_id: 'p-2' },
      move_keys: true,
    })
  })

  it('says why on any other failure and stays open', async () => {
    mockSplit([
      () =>
        HttpResponse.json(
          { detail: { code: 'invalid', message: 'Unknown category' } },
          { status: 400 }
        ),
    ])
    const { onDone } = renderSheet()

    await typeNewName('Karelian stew')
    fireEvent.click(moveButton())

    expect(await screen.findByText('Unknown category')).toBeInTheDocument()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('toasts what moved, and Undo calls the undo endpoint', async () => {
    mockSplit()
    let undone = false
    server.use(
      http.post(`${API_URL}/products/reassignments/r-1/undo`, () => {
        undone = true
        return HttpResponse.json({ reassignment_id: 'r-1', restored_item_ids: ['i-1', 'i-2', 'i-3'] })
      })
    )
    renderSheet()

    await typeNewName('Karelian stew')
    fireEvent.click(moveButton())

    expect(await screen.findByText('Moved 3 items to Karelian stew')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))

    await waitFor(() => expect(undone).toBe(true))
    expect(await screen.findByText('Moved 3 items back to Rice pies')).toBeInTheDocument()
  })

  it('says so when the undo is stale', async () => {
    mockSplit()
    server.use(
      http.post(`${API_URL}/products/reassignments/r-1/undo`, () =>
        HttpResponse.json({ detail: { code: 'stale' } }, { status: 409 })
      )
    )
    renderSheet()

    await typeNewName('Karelian stew')
    fireEvent.click(moveButton())
    fireEvent.click(await screen.findByRole('button', { name: 'Undo' }))

    expect(
      await screen.findByText('Could not undo: the items have changed since')
    ).toBeInTheDocument()
  })

  it("notes that the source keeps the cook's shelf life when nothing is left to learn from", async () => {
    mockSplit([
      () =>
        HttpResponse.json(
          splitResponse({ source_shelf_life: { days: 2, source: 'cook', observations_left: 0 } })
        ),
    ])
    renderSheet()

    await typeNewName('Karelian stew')
    fireEvent.click(moveButton())

    expect(
      await screen.findByText('Rice pies still keeps 2 days — check it on the product')
    ).toBeInTheDocument()
  })

  it('has no shelf-life note when the source still has observations', async () => {
    mockSplit()
    renderSheet()

    await typeNewName('Karelian stew')
    fireEvent.click(moveButton())

    await screen.findByText('Moved 3 items to Karelian stew')
    expect(screen.queryByText(/still keeps/)).not.toBeInTheDocument()
  })

  it('names a hand-added group without a chain', () => {
    mockSplit()
    renderSheet({
      sourceGroup: { ...GROUP, kind: 'manual', label: '', store_chain: null },
    })
    expect(
      screen.getByRole('checkbox', { name: 'Also move the 2 other items added by hand' })
    ).toBeChecked()
    expect(screen.queryByText(/Next receipts/)).not.toBeInTheDocument()
  })

  it('reads in Finnish', async () => {
    window.localStorage.setItem('kyokki.language', 'fi')
    mockSplit()
    renderSheet()

    expect(screen.getByRole('heading', { name: 'Siirrä pois tuotteesta Rice pies' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Uusi tuote' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Olemassa oleva tuote' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Siirrä' })).toBeInTheDocument()
    expect(
      screen.getByRole('checkbox', {
        name: 'Siirrä myös 2 muuta kohdetta, jotka tulivat rivillä KARJALANPAISTI (S-group)',
      })
    ).toBeInTheDocument()
  })
})
