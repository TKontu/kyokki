/**
 * Splitting wrongly joined items off a product (CL8 L3): the sources it is grouped by, the
 * split itself and its undo. A split or an undo moves stock and its history between two
 * products, so both refresh the products, the stock lists and the consumption log.
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { productKeys } from '../useProducts'
import { useProductSources, useSplitProduct, useUndoReassignment } from '../useProductSplit'
import type { ProductSources } from '@/types/product'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

function invalidated(queryClient: QueryClient) {
  const spy = jest.spyOn(queryClient, 'invalidateQueries')
  return () => spy.mock.calls.map(([filters]) => filters?.queryKey)
}

const SOURCES: ProductSources = {
  product_id: 'p-1',
  sources: [
    {
      key: 'line:s-group:karjalanpaisti',
      label: 'KARJALANPAISTI',
      store_chain: 's-group',
      kind: 'receipt',
      item_ids: ['i-1', 'i-2'],
      active_count: 2,
      total_count: 3,
      first_seen: '2026-09-30',
      last_seen: '2026-10-06',
    },
  ],
}

it('reads the product sources under the product keys', async () => {
  server.use(http.get(`${API_URL}/products/p-1/sources`, () => HttpResponse.json(SOURCES)))
  const queryClient = new QueryClient()
  const { result } = renderHook(() => useProductSources('p-1'), {
    wrapper: wrapper(queryClient),
  })

  await waitFor(() => expect(result.current.data).toEqual(SOURCES))
  // Under productKeys.all, so a split's own invalidation refreshes the list too
  expect(queryClient.getQueryData([...productKeys.all, 'sources', 'p-1'])).toEqual(SOURCES)
})

it('does not fetch sources without a product', () => {
  const queryClient = new QueryClient()
  const { result } = renderHook(() => useProductSources(null), {
    wrapper: wrapper(queryClient),
  })
  expect(result.current.fetchStatus).toBe('idle')
})

it('split posts the contract body and invalidates products, stock and history', async () => {
  let body: unknown
  server.use(
    http.post(`${API_URL}/products/p-1/split`, async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ reassignment_id: 'r-1', moved_item_ids: ['i-1'] })
    })
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useSplitProduct(), { wrapper: wrapper(queryClient) })

  await act(async () => {
    await result.current.mutateAsync({
      productId: 'p-1',
      body: {
        item_ids: ['i-1'],
        target: { new: { name: 'Karelian stew', category: 'ready_meals' } },
        move_keys: true,
      },
    })
  })

  expect(body).toEqual({
    item_ids: ['i-1'],
    target: { new: { name: 'Karelian stew', category: 'ready_meals' } },
    move_keys: true,
  })
  expect(keys()).toEqual(
    expect.arrayContaining([productKeys.all, ['inventory'], ['consumption-log']])
  )
})

it('undo posts to the reassignment and invalidates the same keys', async () => {
  let called = false
  server.use(
    http.post(`${API_URL}/products/reassignments/r-1/undo`, () => {
      called = true
      return HttpResponse.json({ reassignment_id: 'r-1', restored_item_ids: ['i-1'] })
    })
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useUndoReassignment(), { wrapper: wrapper(queryClient) })

  await act(async () => {
    await result.current.mutateAsync('r-1')
  })

  expect(called).toBe(true)
  expect(keys()).toEqual(
    expect.arrayContaining([productKeys.all, ['inventory'], ['consumption-log']])
  )
})
