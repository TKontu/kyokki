/**
 * Consumption rules shared by the ConsumptionSheet and the optimistic cache update.
 * The status rules mirror backend/app/crud/inventory_item.py consume_inventory_item.
 */

import type { InventoryItem, Unit } from '@/types/inventory'

export type ConsumptionOptionKey =
  | 'quarter'
  | 'half'
  | 'threeQuarters'
  | 'one'
  | 'two'
  | 'three'
  | 'done'

export interface ConsumptionOption {
  key: ConsumptionOptionKey
  label: string
  amount: number
  disabled: boolean
}

const PROPORTIONAL: { key: ConsumptionOptionKey; label: string; fraction: number }[] = [
  { key: 'quarter', label: '¼', fraction: 0.25 },
  { key: 'half', label: '½', fraction: 0.5 },
  { key: 'threeQuarters', label: '¾', fraction: 0.75 },
]

const COUNTS: { key: ConsumptionOptionKey; label: string; count: number }[] = [
  { key: 'one', label: '−1', count: 1 },
  { key: 'two', label: '−2', count: 2 },
  { key: 'three', label: '−3', count: 3 },
]

/** Below this share of the initial quantity an item is "partial" (backend rule). */
const PARTIAL_THRESHOLD = 0.75

/** Units counted in whole pieces rather than portions. */
export function isCountable(unit: Unit | string): boolean {
  return unit === 'pcs' || unit === 'unit'
}

/** Round to two decimals, matching the backend Numeric(10, 2) columns. */
export function roundQuantity(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

/** Whole numbers without decimals; otherwise up to two decimals with trailing zeros trimmed. */
export function formatQuantity(value: number): string {
  if (Number.isInteger(value)) {
    return value.toString()
  }
  return parseFloat(value.toFixed(2)).toString()
}

function isInactive(item: InventoryItem): boolean {
  return item.status === 'empty' || item.status === 'discarded' || item.current_quantity <= 0
}

/** The buttons offered for an item: ¼ ½ ¾ Done, or −1 −2 −3 Done for countable units. */
export function consumptionOptions(item: InventoryItem): ConsumptionOption[] {
  const inactive = isInactive(item)
  const remaining = roundQuantity(item.current_quantity)

  const partial: ConsumptionOption[] = isCountable(item.unit)
    ? COUNTS.map(({ key, label, count }) => ({
        key,
        label,
        amount: count,
        // A count equal to what is left is the same as Done
        disabled: inactive || count >= remaining,
      }))
    : PROPORTIONAL.map(({ key, label, fraction }) => ({
        key,
        label,
        amount: Math.min(roundQuantity(fraction * item.initial_quantity), remaining),
        disabled: inactive,
      }))

  return [...partial, { key: 'done', label: 'Done', amount: remaining, disabled: inactive }]
}

function todayIsoDate(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/** The item as the backend will return it after consuming `amount`. Pure. */
export function applyConsume(item: InventoryItem, amount: number): InventoryItem {
  const remaining = Math.max(0, roundQuantity(item.current_quantity - amount))

  if (remaining === 0) {
    return { ...item, current_quantity: 0, status: 'empty' }
  }

  if (remaining >= item.initial_quantity) {
    return { ...item, current_quantity: remaining }
  }

  return {
    ...item,
    current_quantity: remaining,
    opened_date: item.status === 'sealed' ? todayIsoDate() : item.opened_date,
    status: remaining / item.initial_quantity < PARTIAL_THRESHOLD ? 'partial' : 'opened',
  }
}
