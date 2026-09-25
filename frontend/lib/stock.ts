/**
 * Stock rules: what is hidden, how items are sorted, and the location choices forms offer.
 * Pure functions over inventory items so optimistic cache updates re-render consistently.
 * How the stock screen groups them is `lib/fridge.ts` (V3).
 */

import type { InventoryItem, InventoryLocation } from '@/types/inventory'

/** Location choices for forms, labelled as the stock groups are. */
export const LOCATION_OPTIONS: { value: InventoryLocation; label: string }[] = [
  { value: 'main_fridge', label: 'Fridge' },
  { value: 'freezer', label: 'Freezer' },
  { value: 'pantry', label: 'Pantry' },
]

/**
 * The three choices, plus `current` as its own option when it is not one of them (H04).
 *
 * Without this a location the API invented leaves every radio unchecked: the form looks like it
 * has no answer, and a diff against "what the item already says" never fires. Offering the raw
 * value keeps it visible, keeps it checked, and lets the cook move the item somewhere known.
 */
export function locationOptions(current?: string): { value: string; label: string }[] {
  if (!current || LOCATION_OPTIONS.some((option) => option.value === current)) {
    return LOCATION_OPTIONS
  }
  return [...LOCATION_OPTIONS, { value: current, label: current }]
}

/** Empty or discarded: gone from the kitchen. */
export function isInactive(item: InventoryItem): boolean {
  return item.status === 'empty' || item.status === 'discarded'
}

/**
 * Total order: expiry date, then creation time, then id. Equal-expiry items keep their place
 * across refetches instead of swapping.
 */
export function compareStock(a: InventoryItem, b: InventoryItem): number {
  if (a.expiry_date !== b.expiry_date) return a.expiry_date < b.expiry_date ? -1 : 1
  if (a.created_at !== b.created_at) return a.created_at < b.created_at ? -1 : 1
  if (a.id !== b.id) return a.id < b.id ? -1 : 1
  return 0
}
