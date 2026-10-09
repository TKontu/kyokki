/**
 * The item sheet stays usable after its product is saved (operator, 2026-10-08: "Items name and
 * finnish name is edited and shelf life and category is swapped. Then the edit view is saved /
 * confirmed. Then the below window gets stuck.").
 *
 * Driven from an area's grid against a mocked API that behaves like the real one: the product
 * PATCH re-dates the item and, because the new category keeps in the freezer, moves it there -
 * out of the area the page is showing while its sheet is still open. Then a live update lands.
 * The Save is pressed with the Finnish name field still focused, as on the iPad, where tapping a
 * button does not move focus off the field being typed in.
 */

import React from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import AreaPage from '../area/[id]/page'
import type { InventoryItem } from '@/types/inventory'
import type { ProductMaster } from '@/types/product'

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

const PRODUCT: ProductMaster = {
  id: 'prod-peas',
  canonical_name: 'Peas',
  category: 'produce',
  storage_type: 'refrigerator',
  default_shelf_life_days: 5,
  shelf_life_source: 'category',
  opened_shelf_life_days: null,
  frozen_shelf_life_days: null,
  avg_piece_grams: null,
  pack_grams: null,
  unit_type: 'weight',
  default_unit: 'g',
  default_quantity: 500,
  min_stock_quantity: null,
  reorder_quantity: null,
  off_product_id: null,
  off_data: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

const CATEGORIES = [
  {
    id: 'produce',
    display_name: 'Produce',
    icon: '🥕',
    default_shelf_life_days: 5,
    sort_order: 10,
    default_storage: 'refrigerator',
  },
  {
    id: 'frozen',
    display_name: 'Frozen',
    icon: '🧊',
    default_shelf_life_days: 180,
    sort_order: 20,
    default_storage: 'freezer',
  },
]

function mockServer() {
  let item = { ...PEAS }
  let product = { ...PRODUCT }
  const patches: Partial<ProductMaster>[] = []
  server.use(
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([item])),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)),
    http.get(`${API_URL}/products/prod-peas`, () => HttpResponse.json(product)),
    http.patch(`${API_URL}/products/prod-peas`, async ({ request }) => {
      const body = (await request.json()) as Partial<ProductMaster>
      patches.push(body)
      product = {
        ...product,
        ...body,
        storage_type: body.category === 'frozen' ? 'freezer' : product.storage_type,
        updated_at: '2026-10-08T10:00:00Z',
      }
      // recompute_expiry_for_product: re-dated, and a freezer product's item moves there
      item = {
        ...item,
        product_name: product.canonical_name,
        product_display_names: product.display_names,
        category: product.category,
        category_name: 'Frozen',
        expiry_date: '2099-09-09',
        location: product.storage_type === 'freezer' ? 'freezer' : item.location,
      }
      return HttpResponse.json(product)
    }),
    http.get(`${API_URL}/products/prod-peas/names`, () =>
      HttpResponse.json({ names: [], printed: [] })
    ),
    http.get(`${API_URL}/products/prod-peas/sources`, () =>
      HttpResponse.json({ product_id: 'prod-peas', sources: [] })
    ),
    http.get(`${API_URL}/products/emoji/reference`, () => HttpResponse.json([])),
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
    http.get(`${API_URL}/icon-library/status`, () =>
      HttpResponse.json({ curation_enabled: false, library_count: 0, marked_count: 0 })
    )
  )
  return patches
}

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

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
let scrollTo: jest.SpyInstance
beforeEach(() => {
  window.localStorage.clear()
  // The fridge scrolled down a little, so unpinning the page would show as a scroll back
  scrollTo = jest.spyOn(window, 'scrollTo').mockImplementation(() => {})
  Object.defineProperty(window, 'scrollY', { value: 240, configurable: true })
})
afterEach(() => {
  scrollTo.mockRestore()
  Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
})

it('leaves the item sheet usable after a rename, Finnish name, shelf life and category save', async () => {
  const patches = mockServer()
  const queryClient = renderVeggies()

  fireEvent.click(await screen.findByRole('button', { name: 'More for Peas' }))
  fireEvent.click(screen.getByRole('button', { name: 'Edit item' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Change product details…' }))

  fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Green peas' } })
  fireEvent.change(screen.getByLabelText('Keeps for'), { target: { value: '200' } })
  fireEvent.click(await screen.findByRole('radio', { name: /Frozen/ }))
  const finnish = screen.getByLabelText('Finnish name')
  fireEvent.change(finnish, { target: { value: 'Herneet' } })
  // On the iPad the field keeps focus (and the keyboard stays up) while Save is tapped
  finnish.focus()
  expect(document.activeElement).toBe(finnish)
  const blurred: boolean[] = []
  finnish.addEventListener('focusout', () => blurred.push(finnish.isConnected))
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))

  // Back on the item's own sheet, which follows the saved product
  const sheet = await screen.findByRole('dialog', { name: 'Green peas' })
  expect(patches).toEqual([
    {
      canonical_name: 'Green peas',
      default_shelf_life_days: 200,
      category: 'frozen',
      display_names: { fi: 'Herneet' },
    },
  ])
  // The field was let go of (the keyboard closes) before its sheet went, and the page stayed
  // pinned where it was through the handover back to the item's sheet
  expect(blurred).toEqual([true])
  expect(scrollTo).not.toHaveBeenCalled()
  expect(document.body.style.top).toBe('-240px')

  // The item was re-dated and moved to the freezer: it left this area, its sheet did not
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'More for Green peas' })).not.toBeInTheDocument()
  )
  await waitFor(() => expect(within(sheet).getByLabelText('Expiry')).toHaveValue('2099-09-09'))

  // A live update for the moved item and the product lands while the sheet is open
  await act(() => queryClient.invalidateQueries())

  // Exactly one sheet, holding focus - not the body, and not a field that no longer exists
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
  expect(screen.getAllByTestId('bottom-sheet-backdrop')).toHaveLength(1)
  expect(sheet).toContainElement(document.activeElement as HTMLElement)
  expect(document.body.style.position).toBe('fixed')

  // Its controls respond: the product's sheet opens again and closes back to the item
  fireEvent.click(within(sheet).getByRole('button', { name: 'Change product details…' }))
  const product = await screen.findByRole('dialog', { name: /Green peas/ })
  expect(await within(product).findByLabelText('Keeps for')).toHaveValue(200)
  fireEvent.click(within(product).getByRole('button', { name: 'Cancel' }))
  const again = await screen.findByRole('dialog', { name: 'Green peas' })
  expect(screen.getAllByRole('dialog')).toHaveLength(1)

  // And it closes, releasing the page
  fireEvent.click(within(again).getByRole('button', { name: 'Close' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.queryByTestId('bottom-sheet-backdrop')).not.toBeInTheDocument()
  expect(document.body.getAttribute('style')).toBeNull()
  expect(scrollTo).toHaveBeenCalledTimes(1)
  expect(scrollTo).toHaveBeenCalledWith(0, 240)
})
