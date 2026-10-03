/**
 * Shopping list types
 * Mirror backend schema: /backend/app/schemas/shopping_list_item.py
 */

import type { Vocabulary } from './vocabulary'

/** Canonical units (DEC-1, MVP-U1). The API converts other units on write. */
export type ShoppingUnit = 'dl' | 'tsp' | 'tbsp' | 'g' | 'pcs'

/** How badly it is needed. */
export type ShoppingPriority = 'urgent' | 'normal' | 'low'

/** Why the line is on the list - who or what put it there. */
export type ShoppingSource = 'manual' | 'auto_restock' | 'recipe'

export interface ShoppingListItem {
  id: string // UUID
  product_master_id: string | null // UUID, null for a free-text item
  name: string
  quantity: number // Decimal, sent as a JSON number (DEC-2)
  // Vocabulary fields: the API may grow any of these without a frontend release, and a value
  // this build does not recognise is kept raw rather than guessed at (H04).
  unit: Vocabulary<ShoppingUnit>
  priority: Vocabulary<ShoppingPriority>
  source: Vocabulary<ShoppingSource>
  is_purchased: boolean
  added_at: string // ISO datetime
  purchased_at: string | null // ISO datetime
  // Post-MVP frontier item 13, phase 2: the linked product's name by language code, e.g.
  // {'fi': 'Maito'}; empty for a free-text item or one whose product has none - the iPad
  // falls back to `name` either way (`lib/displayName.ts`). Optional, same as
  // `InventoryItem.product_display_names`: the API always sends it, but a fixture built
  // before this field existed should not fail to typecheck.
  product_display_names?: Record<string, string>
}

export interface ShoppingListItemCreate {
  product_master_id?: string | null // UUID
  name: string
  quantity: number // > 0
  unit: ShoppingUnit
  priority?: ShoppingPriority // default: normal
  source?: ShoppingSource // default: manual
}

export interface ShoppingListItemUpdate {
  product_master_id?: string | null
  name?: string
  quantity?: number // > 0
  unit?: ShoppingUnit
  priority?: ShoppingPriority
  is_purchased?: boolean
}

export interface ShoppingListParams {
  skip?: number
  limit?: number
  priority?: ShoppingPriority
  include_purchased?: boolean
}

/** The sources `POST /api/shopping/generate` understands today (`recipe`, `meal_plan` wait). */
export type ShoppingGenerateSource = 'low_stock'

export interface ShoppingGenerateRequest {
  sources: ShoppingGenerateSource[]
  dry_run?: boolean // default false: plan only, nothing written
}

/**
 * One product the generator looked at, and what came of it.
 * `need`/`on_hand`/`min_stock` are in `unit`, the product's own unit. `reason` is set only on
 * a skipped line.
 */
export interface ShoppingGenerateLine {
  product_id: string
  name: string
  need: number | null
  unit: string
  on_hand: number | null
  min_stock: number
  item_id: string | null
  reason: string | null
}

/**
 * added: new list items. updated: open items raised to the need. unchanged: open items already
 * big enough. skipped: products that could not be counted or placed (`reason` on each line).
 */
export interface ShoppingGenerateResponse {
  added: ShoppingGenerateLine[]
  updated: ShoppingGenerateLine[]
  unchanged: ShoppingGenerateLine[]
  skipped: ShoppingGenerateLine[]
  dry_run: boolean
}
