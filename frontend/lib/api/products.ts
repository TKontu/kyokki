import apiClient, { API_BASE_URL } from './client'
import type {
  CatalogEstimateResponse,
  EmojiReferenceEntry,
  IconRedrawRequest,
  ProductEmojiRequest,
  ProductListParams,
  ProductMaster,
  ProductMasterUpdate,
  ProductNames,
  ProductSources,
  ProductSplitRequest,
  ProductSplitResponse,
  ReassignmentUndoResponse,
} from '@/types/product'

export async function list(params?: ProductListParams): Promise<ProductMaster[]> {
  return apiClient.get<ProductMaster[]>('/products', params as Record<string, string | undefined>)
}

export async function get(id: string): Promise<ProductMaster> {
  return apiClient.get<ProductMaster>(`/products/${id}`)
}

/**
 * Correct what the catalog believes about a product (H18).
 *
 * `unit_type` is derived server-side from `default_unit`, so it is never sent: the
 * backend canonicalises the unit and works the type out from it.
 */
export async function update(
  id: string,
  data: ProductMasterUpdate
): Promise<ProductMaster> {
  return apiClient.patch<ProductMaster>(`/products/${id}`, data)
}

/**
 * Which products a catalog estimate asks about (Q19). `guesses`: only category
 * placeholders (Q11). `all`: every product whose shelf life the cook did not set.
 */
export type EstimateScope = 'guesses' | 'all'

/**
 * Ask the model what the catalog's shelf lives should be (Q11, Q19).
 *
 * A number the cook set is never sent, in either scope. `apply` defaults to false, so
 * the first call proposes and a second one writes.
 */
export async function estimate(
  apply = false,
  scope: EstimateScope = 'guesses'
): Promise<CatalogEstimateResponse> {
  return apiClient.post<CatalogEstimateResponse>(
    `/products/estimate?apply=${apply}&scope=${scope}`,
    {}
  )
}

/** The names and printed receipt names that resolve to a product (H52). */
export async function names(id: string): Promise<ProductNames> {
  return apiClient.get<ProductNames>(`/products/${id}/names`)
}

/** Stop a learned name meaning this product. The canonical name answers 409. */
export async function forgetName(id: string, nameId: string): Promise<void> {
  return apiClient.delete<void>(`/products/${id}/names/${nameId}`)
}

/** Stop a printed receipt name resolving to this product. */
export async function forgetPrintedName(id: string, aliasId: string): Promise<void> {
  return apiClient.delete<void>(`/products/${id}/aliases/${aliasId}`)
}

/**
 * Where a product's generated icon is served (Q18-G2), for an `<img src>`.
 *
 * The version is part of the URL, so a Regenerate is a new URL and never the cached old one.
 * An `<img>` cannot send the bearer token, but it does not need to: the middleware adds it
 * server-side to every same-origin `/api` request. Never fetch this into the DOM as markup.
 */
export function iconUrl(productId: string, version: number): string {
  return `${API_BASE_URL}/products/${encodeURIComponent(productId)}/icon.png?v=${version}`
}

/**
 * Regenerate the product's icon (Q18-G2), optionally in the cook's words. Always a new random
 * seed. Answers at once with `icon_status: 'pending'`; the image lands in the background
 * minutes later. 409 when generation is not configured (`COMFYUI_BASE_URL` empty).
 */
export async function redrawIcon(id: string, hint?: string | null): Promise<ProductMaster> {
  const body: IconRedrawRequest = { hint: hint?.trim() ? hint.trim() : null }
  return apiClient.post<ProductMaster>(`/products/${id}/icon`, body)
}

/** Use the category emoji instead: the tile shows it until the cook regenerates. */
export async function clearIcon(id: string): Promise<ProductMaster> {
  return apiClient.delete<ProductMaster>(`/products/${id}/icon`)
}

/** The pickable emoji (Q18 build): the product edit sheet's picker. */
export async function emojiReference(): Promise<EmojiReferenceEntry[]> {
  return apiClient.get<EmojiReferenceEntry[]>('/products/emoji/reference')
}

/**
 * The cook's own emoji choice (Q18 build): an emoji sets `cook`, null sets `cleared`.
 * Neither is ever overwritten by a table lookup or a backfill again.
 */
export async function setEmoji(id: string, emoji: string | null): Promise<ProductMaster> {
  const body: ProductEmojiRequest = { emoji }
  return apiClient.put<ProductMaster>(`/products/${id}/emoji`, body)
}

/** Confirm the model's proposal (Q18 build): it becomes exact and shows on the tile. */
export async function confirmEmoji(id: string): Promise<ProductMaster> {
  return apiClient.post<ProductMaster>(`/products/${id}/emoji/confirm`, {})
}

/** Reject the model's proposal (Q18 build): it goes on the gap list. */
export async function rejectEmoji(id: string): Promise<ProductMaster> {
  return apiClient.post<ProductMaster>(`/products/${id}/emoji/reject`, {})
}

/**
 * The display-language codes a product's `display_names` may carry (Post-MVP frontier
 * item 13), e.g. `["fi"]`. English is not among them - it is always `canonical_name`.
 */
export async function languages(): Promise<string[]> {
  return apiClient.get<string[]>('/products/languages')
}

/** Where a product's items came from, grouped (CL8 L3): what the cook may move off it. */
export async function sources(productId: string): Promise<ProductSources> {
  return apiClient.get<ProductSources>(`/products/${productId}/sources`)
}

/**
 * Move items off a product onto an existing product or a new one (CL8 L3). 409 with
 * `detail.code === 'name_exists'` when the new name is already a product's: the caller
 * offers that product instead.
 */
export async function split(
  productId: string,
  body: ProductSplitRequest
): Promise<ProductSplitResponse> {
  return apiClient.post<ProductSplitResponse>(`/products/${productId}/split`, body)
}

/** Reverse a split exactly. 409 `stale` once a moved item has changed product since. */
export async function undoReassignment(id: string): Promise<ReassignmentUndoResponse> {
  return apiClient.post<ReassignmentUndoResponse>(`/products/reassignments/${id}/undo`, {})
}

const productsAPI = {
  list,
  get,
  update,
  estimate,
  names,
  forgetName,
  forgetPrintedName,
  iconUrl,
  redrawIcon,
  clearIcon,
  emojiReference,
  setEmoji,
  confirmEmoji,
  rejectEmoji,
  languages,
  sources,
  split,
  undoReassignment,
}
export default productsAPI
