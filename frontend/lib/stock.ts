/**
 * Stock rules: what is hidden, how items are sorted, and the location choices forms offer.
 * Pure functions over inventory items so optimistic cache updates re-render consistently.
 * How the stock screen groups them is `lib/fridge.ts` (V3).
 *
 * `locationOptions` takes an optional `Language` (review F1, round 2026-10-03-1): the
 * planner's original spec never granted this file, so a Finnish screen still read "Fridge".
 * No hooks here, by design - the caller (already holding `useLanguage()`) passes the language
 * in. Defaulting to `'en'` returns `LOCATION_OPTIONS` by reference, unchanged, for every
 * existing caller.
 */

import type { Language } from '@/lib/language'
import type { InventoryItem, InventoryLocation } from '@/types/inventory'

/** Location choices for forms, labelled as the stock groups are. */
export const LOCATION_OPTIONS: { value: InventoryLocation; label: string }[] = [
  { value: 'main_fridge', label: 'Fridge' },
  { value: 'freezer', label: 'Freezer' },
  { value: 'pantry', label: 'Pantry' },
]

const LOCATION_LABELS_FI: Record<InventoryLocation, string> = {
  main_fridge: 'Jääkaappi',
  freezer: 'Pakastin',
  pantry: 'Komero',
}

function translatedLocationOptions(): { value: InventoryLocation; label: string }[] {
  return LOCATION_OPTIONS.map((option) => ({
    value: option.value,
    label: LOCATION_LABELS_FI[option.value],
  }))
}

/**
 * The three choices, plus `current` as its own option when it is not one of them (H04).
 *
 * Without this a location the API invented leaves every radio unchecked: the form looks like it
 * has no answer, and a diff against "what the item already says" never fires. Offering the raw
 * value keeps it visible, keeps it checked, and lets the cook move the item somewhere known.
 */
export function locationOptions(
  current?: string,
  language: Language = 'en'
): { value: string; label: string }[] {
  const base = language === 'fi' ? translatedLocationOptions() : LOCATION_OPTIONS
  if (!current || base.some((option) => option.value === current)) {
    return base
  }
  return [...base, { value: current, label: current }]
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
