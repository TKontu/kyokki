/**
 * Product search, categories and the quick-add mutation (MVP-S3).
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { SEARCH_DEBOUNCE_MS, useProductSearch } from '../useProducts'
import { useCategories } from '../useCategories'
import { useQuickAddInventoryItem, inventoryKeys } from '../useInventory'
import { useDebouncedValue } from '../useDebouncedValue'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  jest.useRealTimers()
})
afterAll(() => server.close())

function wrapperWith(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

describe('useDebouncedValue', () => {
  it('only settles after the delay', () => {
    jest.useFakeTimers()
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 250), {
      initialProps: { value: 'm' },
    })
    rerender({ value: 'mil' })
    expect(result.current).toBe('m')

    act(() => {
      jest.advanceTimersByTime(249)
    })
    expect(result.current).toBe('m')
    act(() => {
      jest.advanceTimersByTime(1)
    })
    expect(result.current).toBe('mil')
  })
})

describe('useProductSearch', () => {
  it('does not query for an empty term', () => {
    // Fake timers, not a 300 ms sleep: the assertion is that nothing happened, so there is no
    // network to wait for and a real wait only bought flakiness on a loaded machine (H06).
    jest.useFakeTimers()
    const seen: string[] = []
    server.use(
      http.get(`${API_URL}/products`, ({ request }) => {
        seen.push(request.url)
        return HttpResponse.json([])
      })
    )
    const { result } = renderHook(() => useProductSearch('   '), {
      wrapper: wrapperWith(newClient()),
    })

    act(() => {
      jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS * 2)
    })
    expect(seen).toHaveLength(0)
    expect(result.current.data).toBeUndefined()
  })

  it('searches by the trimmed term', async () => {
    const searches: (string | null)[] = []
    server.use(
      http.get(`${API_URL}/products`, ({ request }) => {
        searches.push(new URL(request.url).searchParams.get('search'))
        return HttpResponse.json([])
      })
    )
    const { result } = renderHook(() => useProductSearch(' milk '), {
      wrapper: wrapperWith(newClient()),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(searches).toEqual(['milk'])
  })
})

describe('useCategories', () => {
  it('loads categories', async () => {
    server.use(
      http.get(`${API_URL}/categories`, () =>
        HttpResponse.json([
          {
            id: 'dairy',
            display_name: 'Dairy & Eggs',
            icon: '🥛',
            default_shelf_life_days: 7,
            meal_contexts: null,
            sort_order: 1,
            default_storage: 'refrigerator',
          },
        ])
      )
    )
    const { result } = renderHook(() => useCategories(), { wrapper: wrapperWith(newClient()) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0].default_storage).toBe('refrigerator')
  })
})

describe('useQuickAddInventoryItem', () => {
  it('posts once, normalises the item and refreshes lists and products', async () => {
    let posts = 0
    server.use(
      http.post(`${API_URL}/inventory/quick-add`, () => {
        posts += 1
        return HttpResponse.json(
          { id: 'item-1', product_name: 'Milk', initial_quantity: '10', current_quantity: '10' },
          { status: 201 }
        )
      })
    )
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useQuickAddInventoryItem(), {
      wrapper: wrapperWith(queryClient),
    })

    let item: Awaited<ReturnType<typeof result.current.mutateAsync>> | undefined
    await act(async () => {
      item = await result.current.mutateAsync({ name: 'Milk', category: 'dairy', quantity: 10, unit: 'dl' })
    })

    expect(posts).toBe(1)
    expect(item?.current_quantity).toBe(10)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: inventoryKeys.lists() })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['products'] })
  })

  it('does not retry a failed add', async () => {
    let posts = 0
    server.use(
      http.post(`${API_URL}/inventory/quick-add`, () => {
        posts += 1
        return HttpResponse.json({ detail: 'boom' }, { status: 500 })
      })
    )
    // Even with a client default of one retry, adding stock must not be sent twice
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: 1 } } })
    const { result } = renderHook(() => useQuickAddInventoryItem(), {
      wrapper: wrapperWith(queryClient),
    })

    await act(async () => {
      await result.current.mutateAsync({ name: 'Milk', quantity: 1, unit: 'pcs' }).catch(() => {})
    })

    expect(posts).toBe(1)
  })
})
