/**
 * Regenerate and Use category emoji (Q18-G2) refresh the product and the tiles that show its
 * icon. The exact emoji (Q18 build) - the picker, the cook's choice, confirm and reject -
 * refresh the same way.
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import {
  productKeys,
  useClearProductIcon,
  useConfirmProductEmoji,
  useEmojiReference,
  useRedrawProductIcon,
  useRejectProductEmoji,
  useSetProductEmoji,
} from '../useProducts'

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

it('useEmojiReference lists the pickable emoji', async () => {
  server.use(
    http.get(`${API_URL}/products/emoji/reference`, () =>
      HttpResponse.json([{ emoji: '🥦', name: 'broccoli' }])
    )
  )
  const queryClient = new QueryClient()
  const { result } = renderHook(() => useEmojiReference(), {
    wrapper: wrapper(queryClient),
  })

  await waitFor(() => expect(result.current.data).toEqual([{ emoji: '🥦', name: 'broccoli' }]))
})

it('useSetProductEmoji sends the choice and invalidates products and inventory', async () => {
  let body: unknown
  server.use(
    http.put(`${API_URL}/products/p-1/emoji`, async ({ request }) => {
      body = await request.json()
      return HttpResponse.json({ id: 'p-1', emoji: '🥨', emoji_match: 'cook' })
    })
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useSetProductEmoji(), {
    wrapper: wrapper(queryClient),
  })

  await act(async () => {
    await result.current.mutateAsync({ id: 'p-1', emoji: '🥨' })
  })

  expect(body).toEqual({ emoji: '🥨' })
  expect(keys()).toEqual(expect.arrayContaining([productKeys.all, ['inventory']]))
})

it('useConfirmProductEmoji confirms and invalidates products and inventory', async () => {
  let called = false
  server.use(
    http.post(`${API_URL}/products/p-1/emoji/confirm`, () => {
      called = true
      return HttpResponse.json({ id: 'p-1', emoji: '🥨', emoji_match: 'exact' })
    })
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useConfirmProductEmoji(), {
    wrapper: wrapper(queryClient),
  })

  await act(async () => {
    await result.current.mutateAsync('p-1')
  })

  expect(called).toBe(true)
  expect(keys()).toEqual(expect.arrayContaining([productKeys.all, ['inventory']]))
})

it('useRejectProductEmoji rejects and invalidates products and inventory', async () => {
  let called = false
  server.use(
    http.post(`${API_URL}/products/p-1/emoji/reject`, () => {
      called = true
      return HttpResponse.json({ id: 'p-1', emoji: null, emoji_match: 'none' })
    })
  )
  const queryClient = new QueryClient()
  const keys = invalidated(queryClient)
  const { result } = renderHook(() => useRejectProductEmoji(), {
    wrapper: wrapper(queryClient),
  })

  await act(async () => {
    await result.current.mutateAsync('p-1')
  })

  expect(called).toBe(true)
  expect(keys()).toEqual(expect.arrayContaining([productKeys.all, ['inventory']]))
})
