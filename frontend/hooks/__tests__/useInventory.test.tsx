/**
 * useInventory Hook Tests
 * Using fetch mocks instead of MSW for simplicity
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  INVENTORY_POLL_MS,
  INVENTORY_LIVE_POLL_MS,
  inventoryKeys,
  useInventoryList,
  useInventoryItem,
  useCreateInventoryItem,
  useUpdateInventoryItem,
  useConsumeInventoryItem,
  useDeleteInventoryItem,
  useUnconsumeInventoryItem,
} from '../useInventory'
import { setLiveStatus, resetLiveStatusForTests } from '@/lib/live'
import type { InventoryItem, InventoryItemCreate } from '@/types/inventory'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

// Mock data
const mockInventoryItem: InventoryItem = {
  id: '123e4567-e89b-12d3-a456-426614174000',
  product_master_id: '123e4567-e89b-12d3-a456-426614174001',
  product_name: 'Test Milk 1L',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: '🥛',
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 750,
  unit: 'dl',
  status: 'opened',
  purchase_date: '2024-01-01',
  expiry_date: '2024-01-15',
  expiry_source: 'calculated',
  opened_date: '2024-01-05',
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2024-01-01T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
}

// Mock global fetch
global.fetch = jest.fn()

// Test wrapper with QueryClient
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  })

  function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
  return Wrapper
}

describe('useInventory Hooks', () => {
  beforeEach(() => {
    ;(global.fetch as jest.Mock).mockClear()
  })

  describe('useInventoryList', () => {
    it('should fetch inventory list', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [mockInventoryItem],
      })

      const { result } = renderHook(() => useInventoryList(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))

      expect(result.current.data).toHaveLength(1)
      expect(result.current.data?.[0].id).toBe(mockInventoryItem.id)
    })

    it('polls so a wall-mounted iPad nobody touches still shows current stock', async () => {
      // The fridge display is never focused and never reloaded; without this it shows
      // whatever was true when it was last opened.
      jest.useFakeTimers()
      ;(global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => [mockInventoryItem],
      })

      const { result } = renderHook(() => useInventoryList(), { wrapper: createWrapper() })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(global.fetch).toHaveBeenCalledTimes(1)

      await act(async () => {
        await jest.advanceTimersByTimeAsync(INVENTORY_POLL_MS + 1000)
      })

      expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(1)
      jest.useRealTimers()
    })

    it('refreshes about twice a minute', () => {
      expect(INVENTORY_POLL_MS).toBe(30_000)
    })

    describe('while the live stream is connected (A5)', () => {
      afterEach(() => resetLiveStatusForTests())

      it('relaxes the poll interval instead of stopping it', async () => {
        setLiveStatus('connected')
        jest.useFakeTimers()
        ;(global.fetch as jest.Mock).mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => [mockInventoryItem],
        })

        const { result } = renderHook(() => useInventoryList(), { wrapper: createWrapper() })
        await waitFor(() => expect(result.current.isSuccess).toBe(true))
        expect(global.fetch).toHaveBeenCalledTimes(1)

        await act(async () => {
          await jest.advanceTimersByTimeAsync(INVENTORY_POLL_MS + 1_000)
        })
        // The fallback 30 s interval must not have fired a refetch.
        expect(global.fetch).toHaveBeenCalledTimes(1)

        await act(async () => {
          await jest.advanceTimersByTimeAsync(INVENTORY_LIVE_POLL_MS)
        })
        expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(1)
        jest.useRealTimers()
      })

      it('falls back to the normal poll the moment the stream disconnects', async () => {
        setLiveStatus('connected')
        jest.useFakeTimers()
        ;(global.fetch as jest.Mock).mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => [mockInventoryItem],
        })

        const { result, rerender } = renderHook(() => useInventoryList(), {
          wrapper: createWrapper(),
        })
        await waitFor(() => expect(result.current.isSuccess).toBe(true))

        act(() => setLiveStatus('disconnected'))
        rerender()

        await act(async () => {
          await jest.advanceTimersByTimeAsync(INVENTORY_POLL_MS + 1_000)
        })
        expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(1)
        jest.useRealTimers()
      })

      it('treats "failing" (F8: repeated connection failures) the same as disconnected', async () => {
        setLiveStatus('failing')
        jest.useFakeTimers()
        ;(global.fetch as jest.Mock).mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => [mockInventoryItem],
        })

        const { result } = renderHook(() => useInventoryList(), { wrapper: createWrapper() })
        await waitFor(() => expect(result.current.isSuccess).toBe(true))

        await act(async () => {
          await jest.advanceTimersByTimeAsync(INVENTORY_POLL_MS + 1_000)
        })
        // The normal 30 s poll fired - "failing" gets no special relaxed cadence.
        expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(1)
        jest.useRealTimers()
      })
    })

    it('should handle loading state', () => {
      ;(global.fetch as jest.Mock).mockImplementationOnce(
        () => new Promise(() => {}) // Never resolves
      )

      const { result } = renderHook(() => useInventoryList(), {
        wrapper: createWrapper(),
      })

      expect(result.current.isLoading).toBe(true)
    })
  })

  describe('useInventoryItem', () => {
    it('should fetch single inventory item', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockInventoryItem,
      })

      const { result } = renderHook(() => useInventoryItem(mockInventoryItem.id), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))

      expect(result.current.data?.id).toBe(mockInventoryItem.id)
      expect(result.current.data?.current_quantity).toBe(750)
    })

    it('should not fetch if id is empty', () => {
      const { result } = renderHook(() => useInventoryItem(''), {
        wrapper: createWrapper(),
      })

      expect(result.current.isFetching).toBe(false)
    })
  })

  describe('useCreateInventoryItem', () => {
    it('should create inventory item', async () => {
      const newItemData: InventoryItemCreate = {
        product_master_id: mockInventoryItem.product_master_id,
        initial_quantity: 1000,
        current_quantity: 1000,
        unit: 'dl',
        expiry_date: '2024-02-01',
      }

      const newItem = {
        ...mockInventoryItem,
        id: '123e4567-e89b-12d3-a456-426614174099',
        ...newItemData,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => newItem,
      })

      const { result } = renderHook(() => useCreateInventoryItem(), {
        wrapper: createWrapper(),
      })

      result.current.mutate(newItemData)

      await waitFor(() => expect(result.current.isSuccess).toBe(true))

      expect(result.current.data?.initial_quantity).toBe(1000)
    })
  })

  describe('useUpdateInventoryItem', () => {
    it('should update inventory item', async () => {
      const updateData = { current_quantity: 500, status: 'partial' as const }
      const updatedItem = {
        ...mockInventoryItem,
        ...updateData,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => updatedItem,
      })

      const { result } = renderHook(() => useUpdateInventoryItem(), {
        wrapper: createWrapper(),
      })

      result.current.mutate({
        id: mockInventoryItem.id,
        data: updateData,
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))

      expect(result.current.data?.current_quantity).toBe(500)
      expect(result.current.data?.status).toBe('partial')
    })

    // CL7: a date edit that taught the product a shelf life refreshes the product sheet
    describe('after a date edit', () => {
      async function patchAnswering(learned: unknown) {
        const queryClient = new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
        const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
        const wrapper = ({ children }: { children: React.ReactNode }) => (
          <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        )
        ;(global.fetch as jest.Mock).mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({
            ...mockInventoryItem,
            expiry_date: '2024-01-29',
            learned_shelf_life: learned,
          }),
        })
        const { result } = renderHook(() => useUpdateInventoryItem(), { wrapper })
        result.current.mutate({ id: mockInventoryItem.id, data: { expiry_date: '2024-01-29' } })
        await waitFor(() => expect(result.current.isSuccess).toBe(true))
        return { result, invalidated: invalidate.mock.calls.map(([filters]) => filters?.queryKey) }
      }

      it('invalidates the products when the product learned a shelf life', async () => {
        const learned = {
          product_id: mockInventoryItem.product_master_id,
          old_days: 21,
          new_days: 28,
        }
        const { result, invalidated } = await patchAnswering(learned)

        expect(invalidated).toContainEqual(['products'])
        expect(result.current.data?.learned_shelf_life).toEqual(learned)
      })

      it('leaves the products alone when nothing was learned', async () => {
        const { result, invalidated } = await patchAnswering(null)

        expect(invalidated).not.toContainEqual(['products'])
        expect(result.current.data?.learned_shelf_life).toBeNull()
      })
    })
  })

  describe('useConsumeInventoryItem', () => {
    it('should consume from inventory item', async () => {
      const consumedItem = {
        ...mockInventoryItem,
        current_quantity: 500, // 750 - 250
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => consumedItem,
      })

      const { result } = renderHook(() => useConsumeInventoryItem(), {
        wrapper: createWrapper(),
      })

      result.current.mutate({
        id: mockInventoryItem.id,
        data: { quantity: 250 },
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))

      expect(result.current.data?.current_quantity).toBe(500)
    })

    describe('optimistic list updates', () => {
      function setup() {
        const queryClient = new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
        })
        const otherItem = { ...mockInventoryItem, id: 'other-item', current_quantity: 300 }
        queryClient.setQueryData(inventoryKeys.list(undefined), [mockInventoryItem, otherItem])
        queryClient.setQueryData(inventoryKeys.list({ location: 'main_fridge' }), [
          mockInventoryItem,
        ])
        const wrapper = ({ children }: { children: React.ReactNode }) => (
          <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        )
        return { queryClient, wrapper, otherItem }
      }

      function listItem(queryClient: QueryClient, params: unknown, id: string) {
        const list = queryClient.getQueryData<InventoryItem[]>(
          inventoryKeys.list(params as undefined)
        )
        return list?.find((item) => item.id === id)
      }

      it('updates every cached list before the request resolves', async () => {
        const { queryClient, wrapper, otherItem } = setup()
        let resolveFetch: (value: unknown) => void = () => {}
        ;(global.fetch as jest.Mock).mockReturnValueOnce(
          new Promise((resolve) => {
            resolveFetch = resolve
          })
        )

        const { result } = renderHook(() => useConsumeInventoryItem(), { wrapper })
        act(() => {
          result.current.mutate({ id: mockInventoryItem.id, data: { quantity: 250 } })
        })

        await waitFor(() =>
          expect(listItem(queryClient, undefined, mockInventoryItem.id)?.current_quantity).toBe(500)
        )
        expect(
          listItem(queryClient, { location: 'main_fridge' }, mockInventoryItem.id)?.current_quantity
        ).toBe(500)
        expect(listItem(queryClient, undefined, otherItem.id)?.current_quantity).toBe(300)
        expect(result.current.isPending).toBe(true)

        resolveFetch({
          ok: true,
          status: 200,
          json: async () => ({ ...mockInventoryItem, current_quantity: 500 }),
        })
        await waitFor(() => expect(result.current.isSuccess).toBe(true))
      })

      it('restores every list when the request fails', async () => {
        const { queryClient, wrapper } = setup()
        ;(global.fetch as jest.Mock).mockResolvedValueOnce({
          ok: false,
          status: 400,
          statusText: 'Bad Request',
          json: async () => ({ detail: 'Cannot consume 250 - only 100 available' }),
        })

        const { result } = renderHook(() => useConsumeInventoryItem(), { wrapper })
        act(() => {
          result.current.mutate({ id: mockInventoryItem.id, data: { quantity: 250 } })
        })

        await waitFor(() => expect(result.current.isError).toBe(true))
        expect(listItem(queryClient, undefined, mockInventoryItem.id)?.current_quantity).toBe(750)
        expect(
          listItem(queryClient, { location: 'main_fridge' }, mockInventoryItem.id)?.current_quantity
        ).toBe(750)
        expect(result.current.error?.message).toBe('Cannot consume 250 - only 100 available')
      })

      it('never retries a failed consume, even when the app retries mutations by default', async () => {
        // app/providers.tsx sets mutations.retry = 1. Consuming is not idempotent: a retry after
        // a lost response would consume twice, and a paused retry (hidden tab) hides the error.
        const queryClient = new QueryClient({
          defaultOptions: { queries: { retry: false }, mutations: { retry: 1 } },
        })
        queryClient.setQueryData(inventoryKeys.list(undefined), [mockInventoryItem])
        const wrapper = ({ children }: { children: React.ReactNode }) => (
          <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        )
        ;(global.fetch as jest.Mock).mockResolvedValue({
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
          json: async () => ({}),
        })

        const { result } = renderHook(() => useConsumeInventoryItem(), { wrapper })
        act(() => {
          result.current.mutate({ id: mockInventoryItem.id, data: { quantity: 250 } })
        })

        await waitFor(() => expect(result.current.isError).toBe(true))
        const consumeCalls = (global.fetch as jest.Mock).mock.calls.filter(([url]) =>
          String(url).endsWith('/consume')
        )
        expect(consumeCalls).toHaveLength(1)
        expect(listItem(queryClient, undefined, mockInventoryItem.id)?.current_quantity).toBe(750)
        ;(global.fetch as jest.Mock).mockReset()
      })

      it('invalidates the lists once the mutation settles', async () => {
        const { queryClient, wrapper } = setup()
        const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
        ;(global.fetch as jest.Mock).mockResolvedValueOnce({
          ok: false,
          status: 500,
          statusText: 'Server Error',
          json: async () => ({}),
        })

        const { result } = renderHook(() => useConsumeInventoryItem(), { wrapper })
        act(() => {
          result.current.mutate({ id: mockInventoryItem.id, data: { quantity: 250 } })
        })

        await waitFor(() => expect(result.current.isError).toBe(true))
        expect(invalidate).toHaveBeenCalledWith({ queryKey: inventoryKeys.lists() })
      })
    })
  })

  describe('useDeleteInventoryItem', () => {
    it('should delete inventory item', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 204,
      })

      const { result } = renderHook(() => useDeleteInventoryItem(), {
        wrapper: createWrapper(),
      })

      result.current.mutate(mockInventoryItem.id)

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
    })
  })
})

describe('useUnconsumeInventoryItem (V4: a grey tile tapped back)', () => {
  const USED_UP: InventoryItem = {
    ...mockInventoryItem,
    current_quantity: 0,
    status: 'empty',
    consumed_at: '2026-09-25T08:00:00Z',
  }

  function setup() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    queryClient.setQueryData(inventoryKeys.list({ consumed_since: 'x' }), [USED_UP])
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
    const cached = () =>
      queryClient.getQueryData<InventoryItem[]>(inventoryKeys.list({ consumed_since: 'x' }))?.[0]
    return { wrapper, cached }
  }

  beforeEach(() => (global.fetch as jest.Mock).mockReset())

  it('puts the whole amount back, as a correction', async () => {
    const { wrapper } = setup()
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ ...USED_UP, current_quantity: 1000, status: 'opened', consumed_at: null }),
    })

    const { result } = renderHook(() => useUnconsumeInventoryItem(), { wrapper })
    act(() => result.current.mutate(USED_UP))

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0]
    expect(url).toBe(`${API_URL}/inventory/${USED_UP.id}`)
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body)).toEqual({ current_quantity: 1000 })
  })

  it('shows it back at once, before the server answers', async () => {
    const { wrapper, cached } = setup()
    ;(global.fetch as jest.Mock).mockReturnValueOnce(new Promise(() => {}))

    const { result } = renderHook(() => useUnconsumeInventoryItem(), { wrapper })
    act(() => result.current.mutate(USED_UP))

    await waitFor(() => expect(cached()?.status).toBe('opened'))
    expect(cached()?.current_quantity).toBe(1000)
    expect(cached()?.consumed_at).toBeNull()
  })

  it('leaves it used up when the server says no', async () => {
    const { wrapper, cached } = setup()
    ;(global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({ detail: 'Test Milk 1L has been thrown away' }),
    })

    const { result } = renderHook(() => useUnconsumeInventoryItem(), { wrapper })
    act(() => result.current.mutate(USED_UP))

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(cached()?.status).toBe('empty')
  })
})
