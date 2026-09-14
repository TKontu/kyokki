/**
 * Stock view rules: what is hidden, what is pinned as urgent, how items are grouped and sorted.
 * Pure functions over inventory items so optimistic cache updates re-render consistently.
 */

import { calculateDaysUntilExpiry } from '@/lib/dates'
import type { InventoryItem, InventoryLocation } from '@/types/inventory'

/** Items expiring within this many days (expired included) are pinned on top. */
export const EXPIRING_SOON_DAYS = 3

const LOCATION_GROUPS: { key: string; label: string }[] = [
  { key: 'main_fridge', label: 'Fridge' },
  { key: 'freezer', label: 'Freezer' },
  { key: 'pantry', label: 'Pantry' },
]

const OTHER_GROUP = { key: 'other', label: 'Other' }

/** Location choices for forms, labelled as the stock groups are. */
export const LOCATION_OPTIONS: { value: InventoryLocation; label: string }[] = [
  { value: 'main_fridge', label: 'Fridge' },
  { value: 'freezer', label: 'Freezer' },
  { value: 'pantry', label: 'Pantry' },
]

export interface StockGroup {
  key: string
  label: string
  items: InventoryItem[]
}

export interface StockView {
  expiringSoon: InventoryItem[]
  groups: StockGroup[]
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

export function buildStockView(
  items: InventoryItem[],
  { includeInactive = false }: { includeInactive?: boolean } = {}
): StockView {
  const visible = [...items]
    .filter((item) => includeInactive || !isInactive(item))
    .sort(compareStock)

  const expiringSoon: InventoryItem[] = []
  const byLocation = new Map<string, InventoryItem[]>()

  for (const item of visible) {
    if (calculateDaysUntilExpiry(item.expiry_date) <= EXPIRING_SOON_DAYS) {
      expiringSoon.push(item)
      continue
    }
    const known = LOCATION_GROUPS.some((group) => group.key === item.location)
    const key = known ? item.location : OTHER_GROUP.key
    byLocation.set(key, [...(byLocation.get(key) ?? []), item])
  }

  const groups = [...LOCATION_GROUPS, OTHER_GROUP]
    .map(({ key, label }) => ({ key, label, items: byLocation.get(key) ?? [] }))
    .filter((group) => group.items.length > 0)

  return { expiringSoon, groups }
}
