/**
 * How the shopping screen groups the list it gets back: open items by priority (urgent first),
 * then the bought ones.
 */

import type { ShoppingListItem, ShoppingPriority } from '@/types/shopping'

export interface ShoppingGroup {
  key: string
  label: string
  items: ShoppingListItem[]
}

const PRIORITY_ORDER: Array<{ key: ShoppingPriority; label: string }> = [
  { key: 'urgent', label: 'Urgent' },
  { key: 'normal', label: 'Normal' },
  { key: 'low', label: 'Low' },
]

/**
 * Open items, grouped Urgent / Normal / Low; an empty group is left out. A priority value this
 * build does not recognise (the API may grow the vocabulary without a release, H04) still shows,
 * in its own "Other" group, rather than disappearing from the list.
 */
export function groupOpenItems(items: ShoppingListItem[]): ShoppingGroup[] {
  const open = items.filter((item) => !item.is_purchased)
  const known = new Set<string>(PRIORITY_ORDER.map((group) => group.key))

  const groups: ShoppingGroup[] = PRIORITY_ORDER.map(({ key, label }) => ({
    key,
    label,
    items: open.filter((item) => item.priority === key),
  })).filter((group) => group.items.length > 0)

  const other = open.filter((item) => !known.has(item.priority))
  if (other.length > 0) {
    groups.push({ key: 'other', label: 'Other', items: other })
  }

  return groups
}

/** Bought items, newest first. */
export function boughtItems(items: ShoppingListItem[]): ShoppingListItem[] {
  return items
    .filter((item) => item.is_purchased)
    .sort((a, b) => (b.purchased_at ?? '').localeCompare(a.purchased_at ?? ''))
}
