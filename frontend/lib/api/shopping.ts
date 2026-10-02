/**
 * Shopping list API
 * CRUD and generation over /api/shopping, mirroring backend/app/api/endpoints/shopping.py.
 */

import apiClient from './client'
import type {
  ShoppingGenerateRequest,
  ShoppingGenerateResponse,
  ShoppingListItem,
  ShoppingListItemCreate,
  ShoppingListItemUpdate,
  ShoppingListParams,
} from '@/types/shopping'

/**
 * A fresh key for one user action (create, purchase, an applied generate): a UUID per call, so
 * a retry after a lost response replays the first answer instead of repeating it - the API
 * honours `Idempotency-Key` on these three routes.
 */
export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // A v4-shaped fallback for an environment without crypto.randomUUID. Not cryptographically
  // random, but the API only needs the key to be unique per action.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/** The open list, or every item when `include_purchased` is set (urgent first, per the API). */
export async function list(params?: ShoppingListParams): Promise<ShoppingListItem[]> {
  return apiClient.get<ShoppingListItem[]>(
    '/shopping/',
    params as Record<string, string | number | boolean | undefined>
  )
}

/** All urgent, unpurchased items. */
export async function urgent(): Promise<ShoppingListItem[]> {
  return apiClient.get<ShoppingListItem[]>('/shopping/urgent')
}

/**
 * Add one item to the list. `idempotencyKey` replays the first 201 on a retry within 24 h
 * instead of adding it twice.
 */
export async function create(
  data: ShoppingListItemCreate,
  idempotencyKey: string
): Promise<ShoppingListItem> {
  return apiClient.request<ShoppingListItem>('POST', '/shopping/', {
    body: data,
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

/** Update name, quantity, unit, priority or purchase status. */
export async function update(
  id: string,
  data: ShoppingListItemUpdate
): Promise<ShoppingListItem> {
  return apiClient.patch<ShoppingListItem>(`/shopping/${id}`, data)
}

/**
 * Mark an item bought or not. `idempotencyKey` replays the first answer on a retry for the
 * same item and `purchased` value within 24 h, instead of running it twice.
 */
export async function purchase(
  id: string,
  purchased: boolean,
  idempotencyKey: string
): Promise<ShoppingListItem> {
  return apiClient.request<ShoppingListItem>('POST', `/shopping/${id}/purchase`, {
    params: { purchased },
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

/** Remove one item from the list. */
export async function remove(id: string): Promise<void> {
  return apiClient.delete<void>(`/shopping/${id}`)
}

/** Clear every bought item. */
export async function clearPurchased(): Promise<{ deleted_count: number }> {
  return apiClient.delete<{ deleted_count: number }>('/shopping/purchased/all')
}

/**
 * Put what the kitchen is short of on the list. `dry_run: true` plans without writing, so the
 * screen can show what would change before it happens; `idempotencyKey` is only meaningful (and
 * only needed) on an applied run - a dry run is never remembered by the API.
 */
export async function generate(
  body: ShoppingGenerateRequest,
  idempotencyKey?: string
): Promise<ShoppingGenerateResponse> {
  return apiClient.request<ShoppingGenerateResponse>('POST', '/shopping/generate', {
    body,
    headers: body.dry_run || !idempotencyKey ? undefined : { 'Idempotency-Key': idempotencyKey },
  })
}

const shoppingAPI = {
  list,
  urgent,
  create,
  update,
  purchase,
  remove,
  clearPurchased,
  generate,
  newIdempotencyKey,
}

export default shoppingAPI
