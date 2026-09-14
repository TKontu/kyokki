/**
 * useInventory Hook
 * TanStack Query hooks for inventory management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import inventoryAPI from '@/lib/api/inventory'
import { productKeys } from '@/hooks/useProducts'
import { applyConsume } from '@/lib/consumption'
import type {
  InventoryItem,
  InventoryItemCreate,
  InventoryItemUpdate,
  ConsumeRequest,
  InventoryListParams,
  QuickAddRequest,
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
 * Mutation: Quick add stock, creating the generic product when needed (MVP-S3)
 */
export function useQuickAddInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: QuickAddRequest) => inventoryAPI.quickAdd(data),
    // Adding is not idempotent: a retry after a lost response would add the stock twice.
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
      // The call may have created a product that searches should now find
      queryClient.invalidateQueries({ queryKey: productKeys.all })
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
    // Consuming is not idempotent: retrying after a lost response would consume twice, and
    // TanStack pauses retries while the page is hidden, which leaves the optimistic value up.
    retry: false,
    onMutate: async ({ id, data }) => {
      // Stop in-flight refetches from overwriting the optimistic value
      await Promise.all([
        queryClient.cancelQueries({ queryKey: inventoryKeys.lists() }),
        queryClient.cancelQueries({ queryKey: inventoryKeys.detail(id) }),
      ])

      // Snapshot every cached list (the home page renders from a list, not the detail)
      const previousLists = queryClient.getQueriesData<InventoryItem[]>({
        queryKey: inventoryKeys.lists(),
      })
      const previousItem = queryClient.getQueryData<InventoryItem>(inventoryKeys.detail(id))

      queryClient.setQueriesData<InventoryItem[]>({ queryKey: inventoryKeys.lists() }, (list) =>
        list?.map((item) => (item.id === id ? applyConsume(item, data.quantity) : item))
      )
      if (previousItem) {
        queryClient.setQueryData<InventoryItem>(
          inventoryKeys.detail(id),
          applyConsume(previousItem, data.quantity)
        )
      }

      return { previousLists, previousItem }
    },
    onError: (_err, { id }, context) => {
      // Roll back every list and the detail
      context?.previousLists.forEach(([queryKey, list]) => {
        queryClient.setQueryData(queryKey, list)
      })
      if (context?.previousItem) {
        queryClient.setQueryData(inventoryKeys.detail(id), context.previousItem)
      }
    },
    onSuccess: (updatedItem) => {
      // The server response is authoritative for this item
      queryClient.setQueryData(inventoryKeys.detail(updatedItem.id), updatedItem)
    },
    onSettled: () => {
      // Success or failure, refetch so lists match the server (empty items drop out)
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
    // A retried DELETE after a lost response would only 404; report the first outcome instead.
    retry: false,
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
    onSuccess: (_data, id) => {
      // Drop it from every cached list right away, then refetch to match the server
      queryClient.setQueriesData<InventoryItem[]>({ queryKey: inventoryKeys.lists() }, (list) =>
        list?.filter((item) => item.id !== id)
      )
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
    },
  })
}
