/**
 * useShopping Hook
 * TanStack Query hooks for the shopping list (API done, agent CLI already uses it; this is the
 * iPad screen, frontier item 5).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import shoppingAPI from '@/lib/api/shopping'
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
 *
 * `idempotencyKey` is the caller's to mint and manage (F1): minted once when the user starts
 * the action, and reused by the caller on a retry of that same action, rather than a fresh one
 * generated on every `mutate()` - which is what let a lost response plus a retry add the item
 * twice. Not retried by TanStack either, for the same reason: a retry has to reuse the key the
 * caller chose, not a new one this hook would otherwise mint.
 */
export function useCreateShoppingItem() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Add' },
    mutationFn: ({
      data,
      idempotencyKey,
    }: {
      data: ShoppingListItemCreate
      idempotencyKey: string
    }) => shoppingAPI.create(data, idempotencyKey),
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
 * Mutation: tick an item bought, or untick it (the undo toast's action, and a retry of either,
 * call this again with the same `idempotencyKey` - F1, minted by the caller per action). Marking
 * bought only flips `is_purchased`; it does not touch stock (`shopping_generate.mark_purchased`),
 * so there is nothing in `['inventory']` to invalidate.
 *
 * F3: cancels any in-flight list fetch first, so a response already on the way back cannot land
 * after this mutation's own refetch and show a stale `is_purchased`.
 */
export function usePurchaseShoppingItem() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Bought' },
    mutationFn: ({
      id,
      purchased,
      idempotencyKey,
    }: {
      id: string
      purchased: boolean
      idempotencyKey: string
    }) => shoppingAPI.purchase(id, purchased, idempotencyKey),
    retry: false,
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: shoppingKeys.all })
    },
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
 * written and nothing here is invalidated, and no key is needed - the API never remembers a dry
 * run), then again with `dry_run: false` and an `idempotencyKey` to apply. F1: the caller mints
 * that key once when the apply starts and reuses it for a retry of the same apply.
 */
export function useGenerateShoppingList() {
  const queryClient = useQueryClient()

  return useMutation({
    meta: { label: 'Generate' },
    mutationFn: ({
      idempotencyKey,
      ...body
    }: ShoppingGenerateRequest & { idempotencyKey?: string }) =>
      shoppingAPI.generate(body, body.dry_run ? undefined : idempotencyKey),
    retry: false,
    onSuccess: (result) => {
      if (result.dry_run) return
      queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
    },
  })
}
