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
  iconPollInterval,
  useConfirmProductEmoji,
  useEmojiReference,
  useRedrawProductIcon,
  useRejectProductEmoji,
  useSetProductEmoji,
  useUpdateProduct,
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

describe('useUpdateProduct (operator, 2026-10-07: an edit must show at once)', () => {
  const SAVED = {
    id: 'p-1',
    canonical_name: 'Minced beef',
    default_shelf_life_days: 9,
    updated_at: '2026-10-07T10:00:00Z',
  }

  it('writes the answer into the product and every list that holds it, before any refetch', async () => {
    server.use(http.patch(`${API_URL}/products/p-1`, () => HttpResponse.json(SAVED)))
    const queryClient = new QueryClient()
    const old = { id: 'p-1', canonical_name: 'Ground beef', default_shelf_life_days: 5 }
    const other = { id: 'p-2', canonical_name: 'Pasta', default_shelf_life_days: 700 }
    queryClient.setQueryData(productKeys.detail('p-1'), old)
    queryClient.setQueryData(productKeys.list(undefined), [old, other])
    queryClient.setQueryData(productKeys.list({ search: 'beef' }), [old])
    // Nothing observes these queries, so no refetch can be what changed them
    const { result } = renderHook(() => useUpdateProduct(), { wrapper: wrapper(queryClient) })

    await act(async () => {
      await result.current.mutateAsync({ id: 'p-1', data: { canonical_name: 'Minced beef' } })
    })

    expect(queryClient.getQueryData(productKeys.detail('p-1'))).toEqual(SAVED)
    expect(queryClient.getQueryData(productKeys.list(undefined))).toEqual([SAVED, other])
    expect(queryClient.getQueryData(productKeys.list({ search: 'beef' }))).toEqual([SAVED])
  })

  it('still invalidates products and the stock', async () => {
    server.use(http.patch(`${API_URL}/products/p-1`, () => HttpResponse.json(SAVED)))
    const queryClient = new QueryClient()
    const keys = invalidated(queryClient)
    const { result } = renderHook(() => useUpdateProduct(), { wrapper: wrapper(queryClient) })

    await act(async () => {
      await result.current.mutateAsync({ id: 'p-1', data: { canonical_name: 'Minced beef' } })
    })

    expect(keys()).toEqual(expect.arrayContaining([productKeys.all, ['inventory']]))
  })
})

describe('iconPollInterval', () => {
  it('polls while an icon is rendering', () => {
    expect(iconPollInterval({ icon_status: 'pending', generation_enabled: true })).toBe(5_000)
  })

  it('stops once nothing is pending', () => {
    expect(iconPollInterval({ icon_status: 'ready', generation_enabled: true })).toBe(false)
    expect(iconPollInterval(undefined)).toBe(false)
  })

  it('does not poll for a render this server cannot make', () => {
    // A pending status left over from before generation was switched off never lands
    expect(iconPollInterval({ icon_status: 'pending', generation_enabled: false })).toBe(false)
  })
})
