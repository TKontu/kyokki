/**
 * useInventory Hook
 * TanStack Query hooks for inventory management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import inventoryAPI from '@/lib/api/inventory'
import { consumptionLogKeys } from '@/hooks/useConsumptionLog'
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

/**
 * The stock list is the always-on fridge display: nobody focuses it or reloads it, so it has
 * to refresh itself (MVP-P2). Receipts have their own cadence in `useReceipts.ts`.
 */
export const INVENTORY_POLL_MS = 30_000
/** Short enough that a mount or a regained focus shows fresh stock rather than the cache. */
const INVENTORY_STALE_MS = 10_000

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
    refetchInterval: INVENTORY_POLL_MS,
    staleTime: INVENTORY_STALE_MS,
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
    // Named for the status banner, which offers a failed one back (H45)
    meta: { label: 'Add' },
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
    // Named for the status banner, which offers a failed one back (H45)
    meta: { label: 'Quick add' },
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
    // Named for the status banner, which offers a failed one back (H45)
    meta: { label: 'Save' },
    mutationFn: ({ id, data }: { id: string; data: InventoryItemUpdate }) =>
      inventoryAPI.update(id, data),
    // The only mutation here that used to retry. A correction is not idempotent - a quantity
    // sent twice against a row that moved in between is a different answer - and every other
    // mutation in this file already opts out.
    retry: false,
    onSuccess: (updatedItem) => {
      // Update specific item in cache
      queryClient.setQueryData(inventoryKeys.detail(updatedItem.id), updatedItem)
      // Invalidate lists to reflect changes
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
      queryClient.invalidateQueries({ queryKey: consumptionLogKeys.all })
    },
  })
}

/**
 * Throw several items away at once, and take them back.
 *
 * The clear and its undo are the same shape, which is why they share a hook: the undo passes
 * the ids the clear reported back, so what comes out of the bin is exactly what went in.
 *
 * `retry: false` for the same reason as consume - a retried bulk discard would count `refused`
 * for everything the first attempt got through, and read as a failure.
 */
export function useBulkInventoryMove() {
  const queryClient = useQueryClient()

  return useMutation({
    // Named for the status banner, which offers a failed one back (H45)
    meta: { label: 'Clear' },
    mutationFn: ({ ids, event }: { ids: string[]; event: 'discard' | 'restore' }) =>
      event === 'discard'
        ? inventoryAPI.discardMany(ids)
        : inventoryAPI.restoreMany(ids),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
      queryClient.invalidateQueries({ queryKey: consumptionLogKeys.all })
    },
  })
}

/**
 * Mutation: Consume from inventory item
 */
export function useConsumeInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    // Named for the status banner, which offers a failed one back (H45)
    meta: { label: 'Consume' },
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
      queryClient.invalidateQueries({ queryKey: consumptionLogKeys.all })
    },
  })
}

/**
 * Mutation: bring a used-up item back (V4) - a grey tile tapped in an area's grid.
 *
 * A PATCH that puts the whole amount back: the backend reads it as a correction (H23), which
 * reopens the item, clears `consumed_at`, logs it and leaves it undoable. `restore` would not
 * do: it only brings back what was thrown away, and an empty item restores as empty.
 */
export function useUnconsumeInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Bring back' },
    mutationFn: (item: InventoryItem) =>
      inventoryAPI.update(item.id, { current_quantity: item.initial_quantity }),
    retry: false,
    onMutate: async (item) => {
      await queryClient.cancelQueries({ queryKey: inventoryKeys.lists() })
      const previousLists = queryClient.getQueriesData<InventoryItem[]>({
        queryKey: inventoryKeys.lists(),
      })
      queryClient.setQueriesData<InventoryItem[]>({ queryKey: inventoryKeys.lists() }, (list) =>
        list?.map((cached) =>
          cached.id === item.id
            ? {
                ...cached,
                current_quantity: cached.initial_quantity,
                status: 'opened',
                consumed_at: null,
              }
            : cached
        )
      )
      return { previousLists }
    },
    onError: (_err, _item, context) => {
      context?.previousLists.forEach(([queryKey, list]) => {
        queryClient.setQueryData(queryKey, list)
      })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
      queryClient.invalidateQueries({ queryKey: consumptionLogKeys.all })
    },
  })
}

/**
 * Mutation: Delete inventory item
 */
export function useDeleteInventoryItem() {
  const queryClient = useQueryClient()

  return useMutation({
    // Named for the status banner, which offers a failed one back (H45)
    meta: { label: 'Delete' },
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
      queryClient.invalidateQueries({ queryKey: consumptionLogKeys.all })
    },
  })
}
