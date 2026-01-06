/**
 * Category Types
 * Mirror backend schema: /backend/app/schemas/category.py
 */

export interface Category {
  id: string // Category identifier (e.g., 'dairy', 'meat', 'produce')
  display_name: string // Human-readable name
  icon: string | null // Emoji icon
  default_shelf_life_days: number // > 0
  meal_contexts: string[] | null // e.g., ["breakfast", "lunch"]
  sort_order: number // Display order (default: 0)
}

export interface CategoryCreate {
  id: string // Category identifier
  display_name: string
  icon?: string | null
  default_shelf_life_days: number // > 0
  meal_contexts?: string[] | null
  sort_order?: number // default: 0
}

export interface CategoryUpdate {
  display_name?: string
  icon?: string | null
  default_shelf_life_days?: number // > 0
  meal_contexts?: string[] | null
  sort_order?: number
}
