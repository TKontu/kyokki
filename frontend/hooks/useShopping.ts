/**
 * useShopping Hook
 * TanStack Query hooks for the shopping list (API done, agent CLI already uses it; this is the
 * iPad screen, frontier item 5).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import shoppingAPI, { newIdempotencyKey } from '@/lib/api/shopping'
import type {
  ShoppingGenerateRequest,
  ShoppingListItemCreate,
  ShoppingListItemUpdate,
  ShoppingListParams,
} from '@/types/shopping'

// Query keys factory. Exported so a follow-up (the live-updates PR, #140) can invalidate these
// from the `shopping_list_update` WebSocket message without this hook needing to know about it.
export const shoppingKeys = {
  all: ['shopping'] as const,
  lists: () => [...shoppingKeys.all, 'list'] as const,
  list: (params?: ShoppingListParams) => [...shoppingKeys.lists(), params] as const,
}

/**
 * Query: the shopping list. Pass `{ include_purchased: true }` for the screen, which groups
 * open items by priority itself and shows bought ones collapsed below (the API only offers a
 * presence flag, not a bought-only filter).
 */
export function useShoppingList(params?: ShoppingListParams) {
  return useQuery({
    queryKey: shoppingKeys.list(params),
    queryFn: () => shoppingAPI.list(params),
  })
}

/**
 * Mutation: add an item by name (optionally linked to a product), with amount and unit.
 * Not retried: a retry would need the same Idempotency-Key to stay safe, and a fresh one is
 * generated per call here, so TanStack's own retry would add the item twice.
 */
export function useCreateShoppingItem() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Add' },
    mutationFn: (data: ShoppingListItemCreate) => shoppingAPI.create(data, newIdempotencyKey()),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
    },
  })
}

/** Mutation: correct name, quantity, unit or priority. */
export function useUpdateShoppingItem() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Save' },
    mutationFn: ({ id, data }: { id: string; data: ShoppingListItemUpdate }) =>
      shoppingAPI.update(id, data),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
    },
  })
}

/**
 * Mutation: tick an item bought, or untick it (the undo toast's action calls this again with
 * `purchased: false`). Marking bought only flips `is_purchased`; it does not touch stock
 * (`shopping_generate.mark_purchased`), so there is nothing in `['inventory']` to invalidate.
 */
export function usePurchaseShoppingItem() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Bought' },
    mutationFn: ({ id, purchased }: { id: string; purchased: boolean }) =>
      shoppingAPI.purchase(id, purchased, newIdempotencyKey()),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
    },
  })
}

/** Mutation: remove one item. */
export function useRemoveShoppingItem() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Remove' },
    mutationFn: (id: string) => shoppingAPI.remove(id),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
    },
  })
}

/** Mutation: clear every bought item at once ("Clear bought"). */
export function useClearPurchasedShoppingItems() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Clear bought' },
    mutationFn: () => shoppingAPI.clearPurchased(),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
    },
  })
}

/**
 * Mutation: generate from low stock. Call with `dry_run: true` first to preview (nothing is
 * written and nothing here is invalidated), then again with `dry_run: false` to apply.
 */
export function useGenerateShoppingList() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Generate' },
    mutationFn: (body: ShoppingGenerateRequest) =>
      shoppingAPI.generate(body, body.dry_run ? undefined : newIdempotencyKey()),
    retry: false,
    onSuccess: (result) => {
      if (result.dry_run) return
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
    },
  })
}
