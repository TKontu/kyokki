/**
 * Inventory API
 * CRUD operations for inventory items
 */

import apiClient from './client'
import type {
  BulkItemsResponse,
  ExpirySource,
  InventoryItem,
  InventoryItemCreate,
  InventoryItemStatus,
  InventoryItemUpdate,
  InventoryLocation,
  ConsumeRequest,
  InventoryListParams,
  QuickAddRequest,
  Unit,
} from '@/types/inventory'
import type { UndoPreview, UndoResponse } from '@/types/consumption'
import type { Vocabulary } from '@/types/vocabulary'

/** Every value of each enum the API shares with us, in the order the schemas declare them. */
const UNITS: readonly Unit[] = ['dl', 'tsp', 'tbsp', 'g', 'pcs']
const STATUSES: readonly InventoryItemStatus[] = [
  'sealed',
  'opened',
  'partial',
  'empty',
  'discarded',
]
const EXPIRY_SOURCES: readonly ExpirySource[] = ['scanned', 'calculated', 'manual']
const LOCATIONS: readonly InventoryLocation[] = ['main_fridge', 'freezer', 'pantry']

/**
 * One vocabulary field. Narrows to the union when the API used a value this build knows and
 * keeps the raw string when it did not — never substituting a default, because a wrong label
 * ("Sealed" on a status nobody here recognises) is worse than an unfamiliar one, and every
 * screen renders the raw value (H04). Anything that is not a string at all becomes '' rather
 * than the word "null" or "undefined" on a card.
 */
export function vocabularyValue<T extends string>(
  known: readonly T[],
  raw: unknown
): Vocabulary<T> {
  if (raw === null || raw === undefined) return ''
  const value = typeof raw === 'string' ? raw : String(raw)
  return (known as readonly string[]).includes(value) ? (value as T) : value
}

/**
 * The single place an inventory item from the API is made safe to render.
 *
 * The backend serialises Decimal columns as JSON strings ("1000.00"). Components do
 * arithmetic and `toFixed` on quantities, so coerce them at the API boundary. Also
 * correct if the backend ever switches to JSON numbers (see docs/TODO.md, MVP-S1).
 *
 * The four vocabulary fields are recognised here too, so the screens downstream can assume a
 * string and nothing more.
 */
export function normalizeInventoryItem(raw: InventoryItem): InventoryItem {
  return {
    ...raw,
    initial_quantity: Number(raw.initial_quantity),
    current_quantity: Number(raw.current_quantity),
    unit: vocabularyValue(UNITS, raw.unit),
    status: vocabularyValue(STATUSES, raw.status),
    expiry_source: vocabularyValue(EXPIRY_SOURCES, raw.expiry_source),
    location: vocabularyValue(LOCATIONS, raw.location),
  }
}

/**
 * List inventory items with optional filters
 */
export async function list(params?: InventoryListParams): Promise<InventoryItem[]> {
  const items = await apiClient.get<InventoryItem[]>(
    '/inventory',
    params as Record<string, string | number | boolean | undefined>
  )
  return items.map(normalizeInventoryItem)
}

/**
 * Get a single inventory item by ID
 */
export async function get(id: string): Promise<InventoryItem> {
  return normalizeInventoryItem(await apiClient.get<InventoryItem>(`/inventory/${id}`))
}

/**
 * Create a new inventory item
 */
export async function create(data: InventoryItemCreate): Promise<InventoryItem> {
  return normalizeInventoryItem(await apiClient.post<InventoryItem>('/inventory', data))
}

/**
 * Add stock for an existing or new generic product in one call (MVP-S3)
 */
export async function quickAdd(data: QuickAddRequest): Promise<InventoryItem> {
  return normalizeInventoryItem(
    await apiClient.post<InventoryItem>('/inventory/quick-add', data)
  )
}

/**
 * Update an existing inventory item
 */
export async function update(id: string, data: InventoryItemUpdate): Promise<InventoryItem> {
  return normalizeInventoryItem(
    await apiClient.patch<InventoryItem>(`/inventory/${id}`, data)
  )
}

/**
 * Delete an inventory item
 */
export async function deleteItem(id: string): Promise<void> {
  return apiClient.delete<void>(`/inventory/${id}`)
}

/**
 * Consume a quantity from an inventory item
 */
export async function consume(id: string, data: ConsumeRequest): Promise<InventoryItem> {
  return normalizeInventoryItem(
    await apiClient.post<InventoryItem>(`/inventory/${id}/consume`, data)
  )
}

/**
 * Throw several items away at once, or take them back (H23's events, in bulk).
 *
 * One request rather than one PATCH each: clearing a shelf of expired food would otherwise be
 * a transaction and a broadcast per item, and a failure half way would leave no way to tell
 * what happened. `refused` counts items already in that state - not an error.
 */
export async function discardMany(ids: string[]): Promise<BulkItemsResponse> {
  return apiClient.post<BulkItemsResponse>('/inventory/discard', { ids })
}

export async function restoreMany(ids: string[]): Promise<BulkItemsResponse> {
  return apiClient.post<BulkItemsResponse>('/inventory/restore', { ids })
}

/** What the header's Undo would reverse next, or null when there is nothing to undo. */
export async function undoPreview(): Promise<UndoPreview | null> {
  return apiClient.get<UndoPreview | null>('/inventory/undo')
}

/**
 * Undo the action the preview showed. A 409 means something newer happened in between (or
 * nothing is left to undo): fetch the preview again rather than guess.
 */
export async function undo(batchId: string): Promise<UndoResponse> {
  return apiClient.post<UndoResponse>('/inventory/undo', { batch_id: batchId })
}

// Export as a namespace object for easier imports
const inventoryAPI = {
  list,
  get,
  create,
  quickAdd,
  update,
  delete: deleteItem,
  consume,
  discardMany,
  restoreMany,
  undoPreview,
  undo,
}

export default inventoryAPI
