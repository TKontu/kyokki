/**
 * Icon curation (operator ask 2026-10-03): the status and marks queries, and the
 * mark/unmark mutations - both invalidate the icon-library queries and the product
 * queries (the sheet's own toggle, Settings' list and counts), never `inventory` - a
 * mark changes no stock.
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import {
  iconLibraryKeys,
  useIconLibraryMarks,
  useIconLibraryStatus,
  useMarkIcon,
  useUnmarkIcon,
} from '../useIconLibrary'
import { productKeys } from '../useProducts'

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

it('useIconLibraryStatus reads the status', async () => {
  server.use(
    http.get(`${API_URL}/icon-library/status`, () =>
      HttpResponse.json({ curation_enabled: true, library_count: 3, marked_count: 1 })
    )
  )
  const queryClient = new QueryClient()

  const { result } = renderHook(() => useIconLibraryStatus(), {
    wrapper: wrapper(queryClient),
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data).toEqual({
    curation_enabled: true,
    library_count: 3,
    marked_count: 1,
  })
})

it('useIconLibraryMarks reads the list', async () => {
  server.use(
    http.get(`${API_URL}/icon-library/marks`, () =>
      HttpResponse.json([
        { id: 'p-1', name: 'Quark', icon_version: 1, marked_at: '2026-10-03T00:00:00Z' },
      ])
    )
  )
  const queryClient = new QueryClient()

  const { result } = renderHook(() => useIconLibraryMarks(), {
    wrapper: wrapper(queryClient),
  })

  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data).toHaveLength(1)
})

it('useMarkIcon marks and invalidates icon-library and product queries, not inventory', async () => {
  server.use(
    http.put(`${API_URL}/icon-library/marks/p-1`, () =>
      HttpResponse.json({
        id: 'p-1',
        name: 'Quark',
        icon_version: 1,
        marked_at: '2026-10-03T00:00:00Z',
      })
    )
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useMarkIcon(), { wrapper: wrapper(queryClient) })

  await act(async () => {
    await result.current.mutateAsync('p-1')
  })

  expect(keys()).toEqual(
    expect.arrayContaining([iconLibraryKeys.all, productKeys.all])
  )
  expect(keys()).not.toEqual(expect.arrayContaining([['inventory']]))
})

it('useUnmarkIcon unmarks and invalidates the same queries', async () => {
  server.use(
    http.delete(`${API_URL}/icon-library/marks/p-1`, () =>
      HttpResponse.json({ id: 'p-1', name: 'Quark', icon_version: 1, marked_at: null })
    )
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useUnmarkIcon(), { wrapper: wrapper(queryClient) })

  await act(async () => {
    await result.current.mutateAsync('p-1')
  })

  expect(keys()).toEqual(
    expect.arrayContaining([iconLibraryKeys.all, productKeys.all])
  )
})
