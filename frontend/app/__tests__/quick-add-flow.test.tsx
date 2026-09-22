/**
 * End-to-end quick add on the home page against msw-mocked endpoints (MVP-S3):
 * + Add -> create new product -> Add -> the list refetches and shows it.
 */

import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useProducts'
import Home from '../page'
import type { InventoryItem } from '@/types/inventory'

const PEAS: InventoryItem = {
  id: 'item-peas',
  product_master_id: 'prod-peas',
  product_name: 'Peas',
  category: 'frozen',
  category_name: 'Frozen',
  category_icon: '🧊',
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
  location: 'freezer',
  notes: null,
  created_at: '2026-09-14T10:00:00Z',
  consumed_at: null,
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  jest.useRealTimers()
})
afterAll(() => server.close())

it('adds a new product from the home page and shows it in the list', async () => {
  let stock: InventoryItem[] = []
  server.use(
    http.get(`${API_URL}/receipts`, () => HttpResponse.json([])),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock)),
    http.get(`${API_URL}/products`, () => HttpResponse.json([])),
    http.get(`${API_URL}/categories`, () =>
      HttpResponse.json([
        {
          id: 'frozen',
          display_name: 'Frozen',
          icon: '🧊',
          default_shelf_life_days: 180,
          sort_order: 1,
          default_storage: 'freezer',
        },
      ])
    ),
    http.post(`${API_URL}/inventory/quick-add`, () => {
      stock = [PEAS]
      return HttpResponse.json(PEAS, { status: 201 })
    })
  )
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <Home />
      </ToastProvider>
    </QueryClientProvider>
  )

  fireEvent.click(await screen.findByRole('button', { name: /\+ add/i }))
  // Step over the 250 ms search debounce with fake timers rather than spending it against the
  // findBy budget below; real timers come straight back so msw still answers normally (H06).
  jest.useFakeTimers()
  fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'Peas' } })
  act(() => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
  })
  jest.useRealTimers()
  fireEvent.click(await screen.findByRole('button', { name: 'Create new: Peas' }))
  fireEvent.click(await screen.findByRole('radio', { name: /frozen/i }))
  fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '500' } })
  fireEvent.click(screen.getByRole('radio', { name: 'g' }))
  fireEvent.click(screen.getByRole('button', { name: /^add$/i }))

  expect(await screen.findByText('Added 500 g · Peas')).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(await screen.findByText('Peas')).toBeInTheDocument()
})
