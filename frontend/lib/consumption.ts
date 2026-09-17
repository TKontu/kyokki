/**
 * Consumption rules shared by the ConsumptionSheet and the optimistic cache update.
 * The status rules mirror backend/app/crud/inventory_item.py consume_inventory_item.
 */

import { isInactive as isGone } from '@/lib/stock'
import type { InventoryItem, Unit } from '@/types/inventory'

/** `done` finishes the item; counts are `count-1`, `count-2`, …; fractions keep their names. */
export type ConsumptionOptionKey = string

export interface ConsumptionOption {
  key: ConsumptionOptionKey
  label: string
  amount: number
  disabled: boolean
  /** The act the cook almost always means, rendered large. */
  primary?: boolean
}

const PROPORTIONAL: { key: string; label: string; fraction: number }[] = [
  { key: 'quarter', label: '¼', fraction: 0.25 },
  { key: 'half', label: '½', fraction: 0.5 },
  { key: 'threeQuarters', label: '¾', fraction: 0.75 },
]

/** Eating one is the common case; more than three at a time is what "All" is for. */
const COUNT_LADDER = [1, 2, 3]

/** Below this share of the initial quantity an item is "partial" (backend rule). */
const PARTIAL_THRESHOLD = 0.75

/** Units counted in whole pieces rather than portions (only pcs since MVP-U1). */
export function isCountable(unit: Unit | string): boolean {
  return unit === 'pcs'
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
  return isGone(item) || item.current_quantity <= 0
}

/** Counts below what is left. Taking all of them is the "All n" option, not a count. */
function countOptions(remaining: number): ConsumptionOption[] {
  return COUNT_LADDER.filter((count) => count < remaining).map((count) => ({
    key: `count-${count}`,
    label: String(count),
    amount: count,
    disabled: false,
    primary: count === 1,
  }))
}

/** Fractions of the original amount, capped at what is left and labelled with the amount. */
function fractionOptions(item: InventoryItem, remaining: number): ConsumptionOption[] {
  return PROPORTIONAL.map(({ key, label, fraction }) => {
    const amount = Math.min(roundQuantity(fraction * item.initial_quantity), remaining)
    return {
      key,
      // "½" of a part-used pack is ambiguous; the amount is not
      label: `${label} · ${formatQuantity(amount)} ${item.unit}`,
      amount,
      disabled: false,
    }
  }).filter((option) => option.amount < remaining)
}

/**
 * The buttons offered for an item, derived from its unit and what is actually left (Q4).
 *
 * Pieces lead with a large "1", because eating one apple is what happens; fractions are for
 * things that are poured or spooned. Nothing is offered that would be the same as finishing
 * the item, so there are no dead buttons to read past.
 */
export function consumptionOptions(item: InventoryItem): ConsumptionOption[] {
  const remaining = roundQuantity(item.current_quantity)
  if (isInactive(item)) {
    return [{ key: 'done', label: 'Done', amount: remaining, disabled: true }]
  }

  const countable = isCountable(item.unit)
  const partial = countable ? countOptions(remaining) : fractionOptions(item, remaining)
  const finish: ConsumptionOption = {
    key: 'done',
    label: countable ? `All ${formatQuantity(remaining)}` : 'Done',
    amount: remaining,
    disabled: false,
    // With nothing smaller on offer, finishing it is the only thing to do
    primary: partial.length === 0,
  }
  return [...partial, finish]
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
