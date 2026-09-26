/**
 * Redraw and Use category emoji (Q18) refresh the product and the tiles that show its icon.
 */

import React from 'react'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { productKeys, useClearProductIcon, useRedrawProductIcon } from '../useProducts'

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

it('Redraw sends the hint and invalidates products and inventory', async () => {
  let body: unknown
  server.use(
    http.post(`${API_URL}/products/p-1/icon`, async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ id: 'p-1', icon_status: 'pending' }, { status: 202 })
    })
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useRedrawProductIcon(), {
    wrapper: wrapper(queryClient),
  })

  await act(async () => {
    await result.current.mutateAsync({ id: 'p-1', hint: 'dark loaf' })
  })

  expect(body).toEqual({ hint: 'dark loaf' })
  expect(keys()).toEqual(expect.arrayContaining([productKeys.all, ['inventory']]))
})

it('Use category emoji clears it and invalidates products and inventory', async () => {
  let called = false
  server.use(
    http.delete(`${API_URL}/products/p-1/icon`, () => {
      called = true
      return HttpResponse.json({ id: 'p-1', icon_status: 'cleared', icon_version: null })
    })
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useClearProductIcon(), {
    wrapper: wrapper(queryClient),
  })

  await act(async () => {
    await result.current.mutateAsync('p-1')
  })

  expect(called).toBe(true)
  expect(keys()).toEqual(expect.arrayContaining([productKeys.all, ['inventory']]))
})
