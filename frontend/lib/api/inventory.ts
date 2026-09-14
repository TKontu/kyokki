/**
 * Inventory API
 * CRUD operations for inventory items
 */

import apiClient from './client'
import type {
  InventoryItem,
  InventoryItemCreate,
  InventoryItemUpdate,
  ConsumeRequest,
  InventoryListParams,
  QuickAddRequest,
} from '@/types/inventory'

/**
 * The backend serialises Decimal columns as JSON strings ("1000.00"). Components do
 * arithmetic and `toFixed` on quantities, so coerce them at the API boundary. Also
 * correct if the backend ever switches to JSON numbers (see docs/TODO.md, MVP-S1).
 */
export function normalizeInventoryItem(raw: InventoryItem): InventoryItem {
  return {
    ...raw,
    initial_quantity: Number(raw.initial_quantity),
    current_quantity: Number(raw.current_quantity),
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

// Export as a namespace object for easier imports
const inventoryAPI = {
  list,
  get,
  create,
  quickAdd,
  update,
  delete: deleteItem,
  consume,
}

export default inventoryAPI
