/**
 * useItemSource (Q26): which receipt line an inventory item came from, fetched only for an
 * item that actually has a receipt.
 */

import React from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { useItemSource } from '../useItemSource'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function setup(itemId: string | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderHook(() => useItemSource(itemId), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  })
}

it('fetches the source for an item id', async () => {
  server.use(
    http.get(`${API_URL}/inventory/item-1/source`, () =>
      HttpResponse.json({
        receipt_id: 'r1',
        store_chain: 's-group',
        purchase_date: '2026-09-26',
        line_text: 'KOKKIKARTANO KERMAINEN LOHIKEITTO',
        line_index: 1,
      })
    )
  )

  const { result } = setup('item-1')

  await waitFor(() => expect(result.current.data).toBeDefined())
  expect(result.current.data?.receipt_id).toBe('r1')
  expect(result.current.data?.line_text).toBe('KOKKIKARTANO KERMAINEN LOHIKEITTO')
})

it('does not fetch at all when there is no item id', () => {
  // onUnhandledRequest: 'error' fails the test if this reaches the API anyway
  setup(null)
})

it('resolves null for an item with no receipt', async () => {
  server.use(http.get(`${API_URL}/inventory/item-2/source`, () => HttpResponse.json(null)))

  const { result } = setup('item-2')

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data).toBeNull()
})
