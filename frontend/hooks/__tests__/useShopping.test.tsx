/**
 * useShopping hooks: the list query, and that every mutation invalidates `shoppingKeys.all` -
 * never `['inventory']`, since marking an item bought does not touch stock
 * (`shopping_generate.mark_purchased`).
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import {
  shoppingKeys,
  useClearPurchasedShoppingItems,
  useCreateShoppingItem,
  useGenerateShoppingList,
  usePurchaseShoppingItem,
  useRemoveShoppingItem,
  useShoppingList,
} from '../useShopping'
import type { ShoppingGenerateResponse, ShoppingListItem } from '@/types/shopping'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const ITEM: ShoppingListItem = {
  id: 'i-1',
  product_master_id: null,
  name: 'Bananas',
  quantity: 6,
  unit: 'pcs',
  priority: 'normal',
  source: 'manual',
  is_purchased: false,
  added_at: '2026-10-01T10:00:00Z',
  purchased_at: null,
}

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    queryClient,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  }
}

function invalidatedKeys(queryClient: QueryClient) {
  const spy = jest.spyOn(queryClient, 'invalidateQueries')
  return () => spy.mock.calls.map(([filters]) => filters?.queryKey)
}

describe('shoppingKeys', () => {
  it('builds a stable factory', () => {
    expect(shoppingKeys.all).toEqual(['shopping'])
    expect(shoppingKeys.lists()).toEqual(['shopping', 'list'])
    expect(shoppingKeys.list({ include_purchased: true })).toEqual([
      'shopping',
      'list',
      { include_purchased: true },
    ])
  })
})

describe('useShoppingList', () => {
  it('fetches the list', async () => {
    server.use(http.get(`${API_URL}/shopping/`, () => HttpResponse.json([ITEM])))
    const { Wrapper } = wrapper()

    const { result } = renderHook(() => useShoppingList({ include_purchased: true }), {
      wrapper: Wrapper,
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([ITEM])
  })
})

describe('useCreateShoppingItem', () => {
  it('creates the item with the caller-supplied Idempotency-Key, and invalidates shoppingKeys.all, not inventory', async () => {
    let header: string | null = null
    server.use(
      http.post(`${API_URL}/shopping/`, async ({ request }) => {
        header = request.headers.get('Idempotency-Key')
        return HttpResponse.json(ITEM, { status: 201 })
      })
    )
    const { Wrapper, queryClient } = wrapper()
    const keys = invalidatedKeys(queryClient)

    const { result } = renderHook(() => useCreateShoppingItem(), { wrapper: Wrapper })
    await act(async () => {
      await result.current.mutateAsync({
        data: { name: 'Bananas', quantity: 6, unit: 'pcs' },
        idempotencyKey: 'key-from-caller',
      })
    })

    // F1: the hook forwards the key it was given rather than minting its own, so the caller -
    // the one place that knows whether this is a fresh action or a retry of one - decides it.
    expect(header).toBe('key-from-caller')
    expect(keys()).toEqual([shoppingKeys.all])
  })
})

describe('usePurchaseShoppingItem', () => {
  it('marks an item bought with the caller-supplied key, and invalidates shoppingKeys.all only', async () => {
    let header: string | null = null
    server.use(
      http.post(`${API_URL}/shopping/i-1/purchase`, ({ request }) => {
        header = request.headers.get('Idempotency-Key')
        return HttpResponse.json({ ...ITEM, is_purchased: true })
      })
    )
    const { Wrapper, queryClient } = wrapper()
    const keys = invalidatedKeys(queryClient)

    const { result } = renderHook(() => usePurchaseShoppingItem(), { wrapper: Wrapper })
    const item = await act(() =>
      result.current.mutateAsync({ id: 'i-1', purchased: true, idempotencyKey: 'tick-key' })
    )

    expect(header).toBe('tick-key')
    expect(item.is_purchased).toBe(true)
    expect(keys()).toEqual([shoppingKeys.all])
    expect(keys()).not.toContainEqual(['inventory'])
  })

  it('can undo by marking it not bought again', async () => {
    server.use(
      http.post(`${API_URL}/shopping/i-1/purchase`, ({ request }) => {
        const purchased = new URL(request.url).searchParams.get('purchased')
        return HttpResponse.json({ ...ITEM, is_purchased: purchased === 'true' })
      })
    )
    const { Wrapper } = wrapper()
    const { result } = renderHook(() => usePurchaseShoppingItem(), { wrapper: Wrapper })

    const undone = await act(() =>
      result.current.mutateAsync({ id: 'i-1', purchased: false, idempotencyKey: 'undo-key' })
    )
    expect(undone.is_purchased).toBe(false)
  })

  it('cancels in-flight list queries before purchasing, so a stale refetch cannot overwrite it (F3)', async () => {
    server.use(
      http.post(`${API_URL}/shopping/i-1/purchase`, () =>
        HttpResponse.json({ ...ITEM, is_purchased: true })
      )
    )
    const { Wrapper, queryClient } = wrapper()
    const cancel = jest.spyOn(queryClient, 'cancelQueries')

    const { result } = renderHook(() => usePurchaseShoppingItem(), { wrapper: Wrapper })
    await act(async () => {
      await result.current.mutateAsync({ id: 'i-1', purchased: true, idempotencyKey: 'k' })
    })

    expect(cancel).toHaveBeenCalledWith({ queryKey: shoppingKeys.all })
  })
})

describe('useRemoveShoppingItem', () => {
  it('removes the item and invalidates the list', async () => {
    server.use(
      http.delete(`${API_URL}/shopping/i-1`, () => new HttpResponse(null, { status: 204 }))
    )
    const { Wrapper, queryClient } = wrapper()
    const keys = invalidatedKeys(queryClient)

    const { result } = renderHook(() => useRemoveShoppingItem(), { wrapper: Wrapper })
    await act(async () => {
      await result.current.mutateAsync('i-1')
    })

    expect(keys()).toEqual([shoppingKeys.all])
  })
})

describe('useClearPurchasedShoppingItems', () => {
  it('clears bought items and invalidates the list', async () => {
    server.use(
      http.delete(`${API_URL}/shopping/purchased/all`, () =>
        HttpResponse.json({ deleted_count: 2 })
      )
    )
    const { Wrapper, queryClient } = wrapper()
    const keys = invalidatedKeys(queryClient)

    const { result } = renderHook(() => useClearPurchasedShoppingItems(), { wrapper: Wrapper })
    const response = await act(() => result.current.mutateAsync())

    expect(response).toEqual({ deleted_count: 2 })
    expect(keys()).toEqual([shoppingKeys.all])
  })
})

describe('useGenerateShoppingList', () => {
  const DRY: ShoppingGenerateResponse = {
    added: [],
    updated: [],
    unchanged: [],
    skipped: [],
    dry_run: true,
  }

  it('does not invalidate on a dry run', async () => {
    server.use(http.post(`${API_URL}/shopping/generate`, () => HttpResponse.json(DRY)))
    const { Wrapper, queryClient } = wrapper()
    const keys = invalidatedKeys(queryClient)

    const { result } = renderHook(() => useGenerateShoppingList(), { wrapper: Wrapper })
    await act(async () => {
      await result.current.mutateAsync({ sources: ['low_stock'], dry_run: true })
    })

    expect(keys()).toEqual([])
  })

  it('invalidates shoppingKeys.all once applied', async () => {
    server.use(
      http.post(`${API_URL}/shopping/generate`, () =>
        HttpResponse.json({ ...DRY, dry_run: false })
      )
    )
    const { Wrapper, queryClient } = wrapper()
    const keys = invalidatedKeys(queryClient)

    const { result } = renderHook(() => useGenerateShoppingList(), { wrapper: Wrapper })
    await act(async () => {
      await result.current.mutateAsync({ sources: ['low_stock'], dry_run: false })
    })

    expect(keys()).toEqual([shoppingKeys.all])
  })
})
