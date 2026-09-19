/**
 * Product Master Types
 * Mirror backend schema: /backend/app/schemas/product_master.py
 */

import type { Unit } from './inventory'

export type StorageType = 'refrigerator' | 'freezer' | 'pantry'
export type UnitType = 'volume' | 'weight' | 'count'
export type ShelfLifeSource = 'category' | 'model' | 'cook'

export interface ProductMaster {
  id: string // UUID
  canonical_name: string
  category: string // Category ID
  storage_type: StorageType
  default_shelf_life_days: number // > 0
  opened_shelf_life_days: number | null // > 0 or null
  avg_piece_grams: number | null // Roughly what one piece weighs, when counted (Q2)
  pack_grams: number | null // Roughly what one pack weighs, when measured (Q8)
  // Where the shelf life came from (Q11). `category` is the blanket figure creation had
  // to invent when nothing better was known - a placeholder, not an answer. Read-only:
  // PATCHing the shelf life is what makes it `cook`.
  shelf_life_source: ShelfLifeSource
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
  avg_piece_grams?: number | null // > 0
  pack_grams?: number | null // > 0
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
  avg_piece_grams?: number | null // > 0
  pack_grams?: number | null // > 0
  // unit_type is derived server-side from default_unit; never send it.
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

/** One product a catalog refresh would change, and what to (Q11). */
export interface CatalogEstimateChange {
  id: string
  canonical_name: string
  category: string
  current_days: number
  proposed_days: number
  current_opened: number | null
  proposed_opened: number | null
}

/** What a refresh found. `applied` is false for a dry run, which is the default. */
export interface CatalogEstimateResponse {
  considered: number
  answered: number
  applied: boolean
  changes: CatalogEstimateChange[]
}
