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
} from '@/types/inventory'

/**
 * List inventory items with optional filters
 */
export async function list(params?: InventoryListParams): Promise<InventoryItem[]> {
  return apiClient.get<InventoryItem[]>('/inventory', params)
}

/**
 * Get a single inventory item by ID
 */
export async function get(id: string): Promise<InventoryItem> {
  return apiClient.get<InventoryItem>(`/inventory/${id}`)
}

/**
 * Create a new inventory item
 */
export async function create(data: InventoryItemCreate): Promise<InventoryItem> {
  return apiClient.post<InventoryItem>('/inventory', data)
}

/**
 * Update an existing inventory item
 */
export async function update(id: string, data: InventoryItemUpdate): Promise<InventoryItem> {
  return apiClient.patch<InventoryItem>(`/inventory/${id}`, data)
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
  return apiClient.post<InventoryItem>(`/inventory/${id}/consume`, data)
}

// Export as a namespace object for easier imports
const inventoryAPI = {
  list,
  get,
  create,
  update,
  delete: deleteItem,
  consume,
}

export default inventoryAPI
