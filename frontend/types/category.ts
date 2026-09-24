/**
 * Category Types
 * Mirror backend schema: /backend/app/schemas/category.py
 */

import type { StorageType } from './product'

export interface Category {
  id: string // Category identifier (e.g., 'dairy', 'meat', 'produce')
  display_name: string // Human-readable name
  icon: string | null // Emoji icon
  default_shelf_life_days: number // > 0
  frozen_shelf_life_days: number | null // Days once frozen; null: no useful figure (Q12)
  sort_order: number // Display order (default: 0)
  default_storage: StorageType // Where its products are kept by default (response only)
}

export interface CategoryCreate {
  id: string // Category identifier
  display_name: string
  icon?: string | null
  default_shelf_life_days: number // > 0
  sort_order?: number // default: 0
}

export interface CategoryUpdate {
  display_name?: string
  icon?: string | null
  default_shelf_life_days?: number // > 0
  sort_order?: number
}
