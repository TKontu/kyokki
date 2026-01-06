/**
 * Inventory Item Types
 * Mirror backend schema: /backend/app/schemas/inventory_item.py
 */

export type InventoryItemStatus = 'sealed' | 'opened' | 'partial' | 'empty' | 'discarded'
export type InventoryLocation = 'main_fridge' | 'freezer' | 'pantry'
export type ExpirySource = 'scanned' | 'calculated' | 'manual'
export type Unit = 'ml' | 'g' | 'pcs' | 'unit'

export interface InventoryItem {
  id: string // UUID
  product_master_id: string // UUID
  receipt_id: string | null // UUID
  initial_quantity: number // Decimal
  current_quantity: number // Decimal
  unit: Unit
  status: InventoryItemStatus
  purchase_date: string | null // ISO date
  expiry_date: string // ISO date (required)
  expiry_source: ExpirySource
  opened_date: string | null // ISO date
  batch_number: string | null
  location: InventoryLocation
  notes: string | null
  created_at: string // ISO datetime
  consumed_at: string | null // ISO datetime
}

export interface InventoryItemCreate {
  product_master_id: string // UUID
  receipt_id?: string | null // UUID
  initial_quantity: number // > 0
  current_quantity: number // >= 0
  unit: Unit
  status?: InventoryItemStatus // default: 'sealed'
  purchase_date?: string | null // ISO date
  expiry_date: string // ISO date (required)
  expiry_source?: ExpirySource // default: 'calculated'
  opened_date?: string | null // ISO date
  batch_number?: string | null
  location?: InventoryLocation // default: 'main_fridge'
  notes?: string | null
}

export interface InventoryItemUpdate {
  current_quantity?: number // >= 0
  status?: InventoryItemStatus
  expiry_date?: string // ISO date
  expiry_source?: ExpirySource
  opened_date?: string | null // ISO date
  location?: InventoryLocation
  notes?: string | null
}

export interface ConsumeRequest {
  quantity: number // > 0
}

export interface InventoryListParams {
  location?: InventoryLocation
  status?: InventoryItemStatus
  expiring_days?: number
  context?: string // meal context filter
  category?: string // category filter
}
