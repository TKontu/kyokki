/**
 * An edit shows at once (operator, 2026-10-07: "upon editing item, it does not automatically
 * refresh the products, which gives the impression that the edit did not succeed").
 *
 * Each path drives the real sheets from a tile's "…" against a mocked API whose state changes
 * with every write, and asserts the screen shows the new data without a remount or a reload.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { useStockActions } from '@/hooks/useStockActions'
import type { InventoryItem } from '@/types/inventory'
import type { ProductMaster } from '@/types/product'

const ITEM: InventoryItem = {
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

const PRODUCT: ProductMaster = {
  id: 'prod-oat',
  canonical_name: 'Oat drink',
  category: 'beverages',
  storage_type: 'refrigerator',
  default_shelf_life_days: 10,
  shelf_life_source: 'category',
  opened_shelf_life_days: null,
  frozen_shelf_life_days: null,
  avg_piece_grams: null,
  pack_grams: null,
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

/** A tiny server: every write changes what the next read answers, like the real API. */
function mockServer() {
  let item = { ...ITEM }
  let product = { ...PRODUCT }
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([item])),
    http.patch(`${API_URL}/inventory/item-oat`, async ({ request }) => {
      const body = (await request.json()) as Partial<InventoryItem>
      item = { ...item, ...body }
      return HttpResponse.json(item)
    }),
    http.get(`${API_URL}/products/prod-oat`, () => HttpResponse.json(product)),
    http.patch(`${API_URL}/products/prod-oat`, async ({ request }) => {
      const body = (await request.json()) as Partial<ProductMaster>
      product = { ...product, ...body, updated_at: '2026-10-07T10:00:00Z' }
      // The stock row carries the product's name, as the real list response does
      item = { ...item, product_name: product.canonical_name }
      return HttpResponse.json(product)
    }),
    http.get(`${API_URL}/products/prod-oat/names`, () =>
      HttpResponse.json({ names: [], printed: [] })
    ),
    http.get(`${API_URL}/products/prod-oat/sources`, () =>
      HttpResponse.json({ product_id: 'prod-oat', sources: [] })
    ),
    http.post(`${API_URL}/products/prod-oat/split`, async ({ request }) => {
      const body = (await request.json()) as { target: { new?: { name: string } } }
      const target = {
        ...PRODUCT,
        id: 'prod-stew',
        canonical_name: body.target.new?.name ?? 'New',
      }
      item = { ...item, product_master_id: target.id, product_name: target.canonical_name }
      return HttpResponse.json({
        reassignment_id: 'r-1',
        source_product: product,
        target_product: target,
        target_created: true,
        moved_item_ids: [item.id],
        moved_keys: [],
        source_shelf_life: null,
      })
    }),
    http.get(`${API_URL}/products/emoji/reference`, () => HttpResponse.json([])),
    http.get(`${API_URL}/categories`, () =>
      HttpResponse.json([
        {
          id: 'beverages',
          display_name: 'Beverages',
          icon: '🥤',
          default_shelf_life_days: 10,
          sort_order: 10,
          default_storage: 'refrigerator',
        },
      ])
    ),
    http.get(`${API_URL}/icon-library/status`, () =>
      HttpResponse.json({ curation_enabled: false, library_count: 0, marked_count: 0 })
    )
  )
}

/** The fridge, reduced to what this is about: one tile per item and the shared sheets. */
function Stock() {
  const { items, openMore, sheets } = useStockActions()
  return (
    <>
      <ul aria-label="Stock">
        {(items ?? []).map((item) => (
          <li key={item.id}>
            <span>{`${item.product_name} until ${item.expiry_date.slice(0, 10)}`}</span>
            <button type="button" onClick={() => openMore(item.id)}>
              {`More ${item.id}`}
            </button>
          </li>
        ))}
      </ul>
      {sheets}
    </>
  )
}

function renderStock() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <Stock />
      </ToastProvider>
    </QueryClientProvider>
  )
}

const stock = () => screen.getByRole('list', { name: 'Stock' })

async function openItemSheet() {
  fireEvent.click(await screen.findByRole('button', { name: 'More item-oat' }))
  fireEvent.click(screen.getByRole('button', { name: 'Edit item' }))
  await screen.findByRole('dialog', { name: 'Oat drink' })
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
beforeEach(() => window.localStorage.clear())

describe('an edit shows at once', () => {
  it('(b) an item date edit updates its tile', async () => {
    mockServer()
    renderStock()
    await openItemSheet()

    fireEvent.change(screen.getByLabelText('Expiry'), { target: { value: '2026-10-20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await within(stock()).findByText('Oat drink until 2026-10-20')).toBeInTheDocument()
  })

  it('(c) a product saved from the item sheet updates the item sheet and the tile', async () => {
    mockServer()
    renderStock()
    await openItemSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Change product details…' }))
    const name = await screen.findByLabelText('Name')
    fireEvent.change(name, { target: { value: 'Oat milk' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    // Back on the item's own sheet, which now says the new name
    expect(await screen.findByRole('dialog', { name: 'Oat milk' })).toBeInTheDocument()
    expect(within(stock()).getByText('Oat milk until 2026-09-30')).toBeInTheDocument()
  })

  it('(c) reopening the product details right after a save shows the saved values', async () => {
    mockServer()
    renderStock()
    await openItemSheet()

    fireEvent.click(screen.getByRole('button', { name: 'Change product details…' }))
    fireEvent.change(await screen.findByLabelText('Keeps for'), { target: { value: '21' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await screen.findByRole('button', { name: 'Change product details…' })

    fireEvent.click(screen.getByRole('button', { name: 'Change product details…' }))
    await waitFor(() => expect(screen.getByLabelText('Keeps for')).toHaveValue(21))
  })

  it('(d) a split from the item sheet updates the tile', async () => {
    mockServer()
    renderStock()
    await openItemSheet()

    fireEvent.click(screen.getByRole('button', { name: 'This is not Oat drink…' }))
    fireEvent.change(await screen.findByLabelText('New product name'), {
      target: { value: 'Rice drink' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Move' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await within(stock()).findByText('Rice drink until 2026-09-30')).toBeInTheDocument()
  })
})
