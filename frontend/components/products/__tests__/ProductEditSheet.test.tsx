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
import type { ProductMaster } from '@/types/product'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
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
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ProductEditSheet product={product} onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  return onClose
}

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
