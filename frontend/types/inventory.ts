/**
 * Inventory Item Types
 * Mirror backend schema: /backend/app/schemas/inventory_item.py
 */

import type { Vocabulary } from './vocabulary'

export type InventoryItemStatus = 'sealed' | 'opened' | 'partial' | 'empty' | 'discarded'
export type InventoryLocation = 'main_fridge' | 'freezer' | 'pantry'
// `frozen` is set when an item is moved to the freezer and re-dated from there (Q12).
export type ExpirySource = 'scanned' | 'calculated' | 'manual' | 'frozen'
/** Canonical units (DEC-1, MVP-U1). The API converts other units on write. */
export type Unit = 'dl' | 'tsp' | 'tbsp' | 'g' | 'pcs'

export interface InventoryItem {
  id: string // UUID
  product_master_id: string // UUID
  product_name: string // ProductMaster.canonical_name
  category: string // Category ID, e.g. 'dairy'
  category_name: string // Category display name
  category_icon: string | null // Category emoji
  receipt_id: string | null // UUID
  initial_quantity: number // Decimal, sent as a JSON number (DEC-2)
  current_quantity: number // Decimal, sent as a JSON number (DEC-2)
  // Vocabulary fields on the way in: the API may grow any of these enums without a frontend
  // release, and `normalizeInventoryItem` keeps whatever it sent rather than guessing (H04).
  unit: Vocabulary<Unit>
  status: Vocabulary<InventoryItemStatus>
  purchase_date: string | null // ISO date
  expiry_date: string // ISO date (required)
  expiry_source: Vocabulary<ExpirySource>
  opened_date: string | null // ISO date
  batch_number: string | null
  location: Vocabulary<InventoryLocation>
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

/**
 * POST /inventory/quick-add (MVP-S3): an existing product, or a generic product found or
 * created by name (case-insensitive). A new product needs `category`.
 */
export interface QuickAddRequest {
  product_id?: string // UUID
  name?: string
  category?: string // Category id, required for a new product
  quantity: number // > 0
  unit: string // dl, tsp, tbsp, g, pcs (ml, l, kg, kpl convert on write)
  // A form may offer back a location the API itself sent (an unknown storage type, say). Sending
  // it is better than silently omitting the field; an invalid one comes back as a 400 (H04).
  location?: Vocabulary<InventoryLocation> // default from the product's storage type
  purchase_date?: string // ISO date, default today
  expiry_date?: string // ISO date; omit to calculate from shelf life
}

export interface InventoryItemUpdate {
  current_quantity?: number // >= 0
  status?: InventoryItemStatus
  expiry_date?: string // ISO date
  expiry_source?: ExpirySource
  opened_date?: string | null // ISO date
  // Same as QuickAddRequest: the edit sheet can offer the item's own raw location back (H04)
  location?: Vocabulary<InventoryLocation>
  notes?: string | null
}

export interface ConsumeRequest {
  quantity: number // > 0
}

export interface InventoryListParams {
  location?: InventoryLocation
  status?: InventoryItemStatus
  expiring_days?: number
  include_inactive?: boolean // backend hides empty/discarded unless true
  context?: string // meal context filter
  category?: string // category filter
}
