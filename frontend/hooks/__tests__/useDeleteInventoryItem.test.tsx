/**
 * Deleting stock removes it from cached lists at once and is never retried (MVP-S4).
 */

import React from 'react'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { inventoryKeys, useDeleteInventoryItem } from '../useInventory'
import type { InventoryItem } from '@/types/inventory'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const item = (id: string) => ({ id, product_name: id }) as InventoryItem

function setup(queryClient: QueryClient) {
  return renderHook(() => useDeleteInventoryItem(), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  })
}

it('removes the item from every cached list', async () => {
  server.use(
    http.delete(`${API_URL}/inventory/a`, () => new HttpResponse(null, { status: 204 })),
    http.get(`${API_URL}/inventory`, () => HttpResponse.json([item('b')]))
  )
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  queryClient.setQueryData(inventoryKeys.list(undefined), [item('a'), item('b')])
  queryClient.setQueryData(inventoryKeys.list({ location: 'freezer' }), [item('a')])
  const { result } = setup(queryClient)

  await act(async () => {
    await result.current.mutateAsync('a')
  })

  const lists = queryClient.getQueriesData<InventoryItem[]>({ queryKey: inventoryKeys.lists() })
  for (const [, list] of lists) {
    expect(list?.map((i) => i.id) ?? []).not.toContain('a')
  }
})

it('does not retry a failed delete', async () => {
  let calls = 0
  server.use(
    http.delete(`${API_URL}/inventory/a`, () => {
      calls += 1
      return HttpResponse.json({ detail: 'boom' }, { status: 500 })
    })
  )
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: 1 } } })
  const { result } = setup(queryClient)

  await act(async () => {
    await result.current.mutateAsync('a').catch(() => {})
  })

  expect(calls).toBe(1)
})
