/**
 * Product Master Types
 * Mirror backend schema: /backend/app/schemas/product_master.py
 */

export type StorageType = 'refrigerator' | 'freezer' | 'pantry'
export type UnitType = 'volume' | 'weight' | 'count' | 'unit'
export type Unit = 'ml' | 'g' | 'pcs'

export interface ProductMaster {
  id: string // UUID
  canonical_name: string
  category: string // Category ID
  storage_type: StorageType
  default_shelf_life_days: number // > 0
  opened_shelf_life_days: number | null // > 0 or null
  unit_type: UnitType
  default_unit: Unit
  default_quantity: number | null // > 0 or null
  min_stock_quantity: number | null // >= 0 or null
  reorder_quantity: number | null // > 0 or null
  off_product_id: string | null // Open Food Facts product ID
  off_data: Record<string, unknown> | null // Cached OFF data
  created_at: string // ISO datetime
  updated_at: string // ISO datetime
}

export interface ProductMasterCreate {
  canonical_name: string
  category: string // Category ID (must exist)
  storage_type: StorageType
  default_shelf_life_days: number // > 0
  opened_shelf_life_days?: number | null // > 0
  unit_type: UnitType
  default_unit: Unit
  default_quantity?: number | null // > 0
  min_stock_quantity?: number | null // >= 0
  reorder_quantity?: number | null // > 0
  off_product_id?: string | null
}

export interface ProductMasterUpdate {
  canonical_name?: string
  category?: string
  storage_type?: StorageType
  default_shelf_life_days?: number // > 0
  opened_shelf_life_days?: number | null // > 0
  unit_type?: UnitType
  default_unit?: Unit
  default_quantity?: number | null // > 0
  min_stock_quantity?: number | null // >= 0
  reorder_quantity?: number | null // > 0
  off_product_id?: string | null
}

export interface ProductListParams {
  search?: string
}
