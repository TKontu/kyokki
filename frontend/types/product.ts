/**
 * Product Master Types
 * Mirror backend schema: /backend/app/schemas/product_master.py
 */

import type { Unit } from './inventory'

export type StorageType = 'refrigerator' | 'freezer' | 'pantry'
export type UnitType = 'volume' | 'weight' | 'count'
export type ShelfLifeSource = 'category' | 'model' | 'cook'
// Where a product's drawn icon stands (Q18). `cleared`: the cook chose the category emoji.
export type IconStatus = 'pending' | 'ready' | 'failed' | 'cleared'
// Where a product's exact Apple emoji stands (Q18 build). `exact`: the curated table, or a
// confirmed proposal. `proposed`: the model's answer, not yet confirmed - never shown.
// `none`: the gap list, or a rejected proposal. `cook`: set by hand. `cleared`: the cook
// chose no emoji; nothing proposes one again.
export type EmojiMatch = 'exact' | 'proposed' | 'none' | 'cook' | 'cleared'
// Whose word a learned name is (H51): the product's own, the cook's, or a model guess.
export type NameSource = 'canonical' | 'cook' | 'model'

export interface ProductMaster {
  id: string // UUID
  canonical_name: string
  category: string // Category ID
  storage_type: StorageType
  default_shelf_life_days: number // > 0
  opened_shelf_life_days: number | null // > 0 or null
  // Days it keeps once frozen (H52). Null defers to the category's figure.
  frozen_shelf_life_days: number | null
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
  // The icon the model drew (Q18). Null status: never drawn. `failed` keeps any earlier
  // drawing. A version means there is a drawing to show; null means show the category emoji.
  // Optional so fixtures written before Q18 still type-check.
  icon_status?: IconStatus | null
  icon_version?: number | null
  // The exact Apple emoji (Q18 build), one from GET /products/emoji/reference. The tile and
  // this sheet show it only when emoji_match is 'exact' or 'cook' (lib/productIcon.ts).
  // Optional so fixtures written before this build still type-check.
  emoji?: string | null
  emoji_match?: EmojiMatch | null
  created_at: string // ISO datetime
  updated_at: string // ISO datetime
}

export interface ProductMasterCreate {
  canonical_name: string
  category: string // Category ID (must exist)
  storage_type: StorageType
  default_shelf_life_days: number // > 0
  opened_shelf_life_days?: number | null // > 0
  frozen_shelf_life_days?: number | null // > 0; null falls back to the category
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
  frozen_shelf_life_days?: number | null // > 0; null falls back to the category
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

/** Draw a product's icon again (Q18), optionally in the cook's words. */
export interface IconRedrawRequest {
  hint?: string | null // at most 200 characters
}

export interface ProductListParams {
  search?: string
  // Feeds the "Emoji to confirm" review list (Q18 build), e.g. 'proposed'.
  emoji_match?: EmojiMatch
}

/** The cook's own emoji choice (Q18 build): an emoji sets `cook`, null sets `cleared`. */
export interface ProductEmojiRequest {
  emoji: string | null
}

/** One pickable emoji, for the product edit sheet's picker (Q18 build). */
export interface EmojiReferenceEntry {
  emoji: string
  name: string
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
  // Stock whose expiry moved with the new shelf lives (Q12). Zero on a dry run.
  items_redated: number
  changes: CatalogEstimateChange[]
}

/** A catalog name that resolves to the product (H52). `name` is the normalised key. */
export interface ProductNameEntry {
  id: string
  name: string
  source: NameSource
  removable: boolean // false for the canonical name, which a rename changes instead
}

/** A printed receipt name that resolves to the product (H52). */
export interface PrintedNameEntry {
  id: string
  store_chain: string
  receipt_name: string
  source: string // cook, model or name: who taught it
  verified: boolean
  occurrence_count: number
  last_seen: string | null // ISO datetime
}

/** Everything that makes a line resolve to this product without asking the model. */
export interface ProductNames {
  names: ProductNameEntry[]
  printed: PrintedNameEntry[]
}
