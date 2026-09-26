/**
 * Staleness tiers (V1, operator ask 2026-09-24).
 *
 * The fridge view shows no numbers: a tile's colour says how soon to eat it. Red is going
 * stale (past its date, or two days or fewer left), orange three or four days, green five to
 * seven, blue eight or more, grey used up. A tile is red only in its last two days (operator
 * ruling 2026-09-26, Q19): counting a day earlier made most of a fresh shop red by day two. Every tier also has a word, for screen readers and for anyone who
 * cannot tell red from green - colour is never the only signal.
 */

import { calculateDaysUntilExpiry } from '@/lib/dates'
import type { InventoryItem } from '@/types/inventory'

export type Staleness = 'stale' | 'soon' | 'week' | 'later' | 'consumed'

export interface StalenessStyle {
  /** Said aloud with the name: "Milk, going stale". */
  label: string
  /** Background, border and text for a tile. */
  tile: string
  /** The dot an area card shows for one item. */
  dot: string
}

export const STALENESS: Record<Staleness, StalenessStyle> = {
  stale: {
    label: 'going stale',
    tile: 'bg-red-100 border-red-500 text-red-950 dark:bg-red-950 dark:border-red-400 dark:text-red-50',
    dot: 'bg-red-500 dark:bg-red-400',
  },
  soon: {
    label: 'a couple of days',
    tile: 'bg-orange-100 border-orange-400 text-orange-950 dark:bg-orange-950 dark:border-orange-400 dark:text-orange-50',
    dot: 'bg-orange-400',
  },
  week: {
    label: 'about a week',
    tile: 'bg-green-100 border-green-500 text-green-950 dark:bg-green-950 dark:border-green-400 dark:text-green-50',
    dot: 'bg-green-500 dark:bg-green-400',
  },
  later: {
    label: 'keeps',
    tile: 'bg-blue-100 border-blue-400 text-blue-950 dark:bg-blue-950 dark:border-blue-400 dark:text-blue-50',
    dot: 'bg-blue-400',
  },
  consumed: {
    label: 'used up',
    tile: 'bg-gray-100 border-gray-300 text-gray-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-400',
    dot: 'bg-gray-300 dark:bg-gray-600',
  },
}

export function stalenessOf(item: Pick<InventoryItem, 'expiry_date' | 'status'>): Staleness {
  if (item.status === 'empty') return 'consumed'
  const days = calculateDaysUntilExpiry(item.expiry_date)
  if (days <= 2) return 'stale'
  if (days <= 4) return 'soon'
  if (days <= 7) return 'week'
  return 'later'
}
