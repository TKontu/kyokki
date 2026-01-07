/**
 * useInventory Hook Tests
 * Using fetch mocks instead of MSW for simplicity
 */

import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
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
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 750,
  unit: 'ml',
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
        unit: 'ml',
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
