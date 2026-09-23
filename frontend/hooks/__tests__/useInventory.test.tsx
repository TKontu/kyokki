/**
 * useInventory Hook Tests
 * Using fetch mocks instead of MSW for simplicity
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  INVENTORY_POLL_MS,
  inventoryKeys,
  useInventoryList,
  useInventoryItem,
  useCreateInventoryItem,
  useUpdateInventoryItem,
  useConsumeInventoryItem,
  useDeleteInventoryItem,
} from '../useInventory'
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

  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
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
