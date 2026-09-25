/**
 * Consumption rules for the optimistic cache update. The status rules mirror
 * backend/app/crud/inventory_item.py consume_inventory_item.
 *
 * The UI no longer offers amounts (V2, presence not amounts): a tile tap uses an item up. The
 * fraction and count ladders that fed the old card and sheet went with them; the backend still
 * keeps and checks the amounts, and `applyConsume` still predicts what it will answer.
 */

import { toISODate } from '@/lib/dates'
import type { InventoryItem } from '@/types/inventory'

/** Below this share of the initial quantity an item is "partial" (backend rule). */
const PARTIAL_THRESHOLD = 0.75

/** Round to two decimals, matching the backend Numeric(10, 2) columns. */
export function roundQuantity(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

function todayIsoDate(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/**
 * The expiry once a pack is opened (Q5), mirroring `_start_opened_clock` in
 * backend/app/crud/inventory_item.py.
 *
 * Opening can only bring the date forward - a jar opened the day before its printed date does
 * not gain a fortnight - and **loose produce is not a pack**: taking one apple out of a bowl of
 * thirteen opens nothing, and the tell is the piece weight.
 */
function openedExpiry(item: InventoryItem, openedDate: string): string {
  if (item.avg_piece_grams !== null) return item.expiry_date
  if (item.opened_shelf_life_days === null) return item.expiry_date
  const opened = new Date(openedDate)
  opened.setDate(opened.getDate() + item.opened_shelf_life_days)
  const shortened = toISODate(opened)
  return shortened < item.expiry_date.split('T')[0] ? shortened : item.expiry_date
}

/**
 * The item as the backend will return it after consuming `amount`. Pure.
 *
 * It predicts the opened clock too (H25): without that the card kept the old expiry badge
 * until the refetch landed, and then jumped - sometimes from green straight to red, and out of
 * its shelf into "Expiring soon". One tap does that often enough to matter.
 */
export function applyConsume(item: InventoryItem, amount: number): InventoryItem {
  const remaining = Math.max(0, roundQuantity(item.current_quantity - amount))

  if (remaining === 0) {
    return { ...item, current_quantity: 0, status: 'empty' }
  }

  if (remaining >= item.initial_quantity) {
    return { ...item, current_quantity: remaining }
  }

  const opensThePack = item.status === 'sealed'
  const openedDate = opensThePack ? todayIsoDate() : item.opened_date

  return {
    ...item,
    current_quantity: remaining,
    opened_date: openedDate,
    expiry_date:
      opensThePack && openedDate ? openedExpiry(item, openedDate) : item.expiry_date,
    status: remaining / item.initial_quantity < PARTIAL_THRESHOLD ? 'partial' : 'opened',
  }
}
