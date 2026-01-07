/**
 * useInventory Hook
 * TanStack Query hooks for inventory management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import inventoryAPI from '@/lib/api/inventory'
import type {
  InventoryItem,
  InventoryItemCreate,
  InventoryItemUpdate,
  ConsumeRequest,
  InventoryListParams,
} from '@/types/inventory'

// Query keys factory
export const inventoryKeys = {
  all: ['inventory'] as const,
  lists: () => [...inventoryKeys.all, 'list'] as const,
  list: (params?: InventoryListParams) => [...inventoryKeys.lists(), params] as const,
  details: () => [...inventoryKeys.all, 'detail'] as const,
  detail: (id: string) => [...inventoryKeys.details(), id] as const,
}

/**
 * Query: List inventory items
 */
export function useInventoryList(params?: InventoryListParams) {
  return useQuery({
    queryKey: inventoryKeys.list(params),
    queryFn: () => inventoryAPI.list(params),
  })
}

/**
 * Query: Get single inventory item
 */
export function useInventoryItem(id: string) {
  return useQuery({
    queryKey: inventoryKeys.detail(id),
    queryFn: () => inventoryAPI.get(id),
    enabled: !!id, // Only fetch if id is provided
  })
}

/**
 * Mutation: Create inventory item
 */
export function useCreateInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: InventoryItemCreate) => inventoryAPI.create(data),
    onSuccess: () => {
      // Invalidate all list queries to refetch
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
    },
  })
}

/**
 * Mutation: Update inventory item
 */
export function useUpdateInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: InventoryItemUpdate }) =>
      inventoryAPI.update(id, data),
    onSuccess: (updatedItem) => {
      // Update specific item in cache
      queryClient.setQueryData(inventoryKeys.detail(updatedItem.id), updatedItem)
      // Invalidate lists to reflect changes
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
    },
  })
}

/**
 * Mutation: Consume from inventory item
 */
export function useConsumeInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ConsumeRequest }) =>
      inventoryAPI.consume(id, data),
    onMutate: async ({ id, data }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: inventoryKeys.detail(id) })

      // Snapshot previous value
      const previousItem = queryClient.getQueryData<InventoryItem>(
        inventoryKeys.detail(id)
      )

      // Optimistically update
      if (previousItem) {
        const newQuantity = previousItem.current_quantity - data.quantity
        queryClient.setQueryData<InventoryItem>(inventoryKeys.detail(id), {
          ...previousItem,
          current_quantity: newQuantity,
          status: newQuantity <= 0 ? 'empty' : previousItem.status,
        })
      }

      return { previousItem }
    },
    onError: (err, { id }, context) => {
      // Rollback on error
      if (context?.previousItem) {
        queryClient.setQueryData(inventoryKeys.detail(id), context.previousItem)
      }
    },
    onSuccess: (updatedItem) => {
      // Update cache with server response
      queryClient.setQueryData(inventoryKeys.detail(updatedItem.id), updatedItem)
      // Invalidate lists to reflect changes
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
    },
  })
}

/**
 * Mutation: Delete inventory item
 */
export function useDeleteInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => inventoryAPI.delete(id),
    onMutate: async (id) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: inventoryKeys.detail(id) })

      // Snapshot previous value
      const previousItem = queryClient.getQueryData<InventoryItem>(
        inventoryKeys.detail(id)
      )

      // Optimistically remove from cache
      queryClient.removeQueries({ queryKey: inventoryKeys.detail(id) })

      return { previousItem }
    },
    onError: (err, id, context) => {
      // Rollback on error
      if (context?.previousItem) {
        queryClient.setQueryData(inventoryKeys.detail(id), context.previousItem)
      }
    },
    onSuccess: () => {
      // Invalidate lists to reflect deletion
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
    },
  })
}
