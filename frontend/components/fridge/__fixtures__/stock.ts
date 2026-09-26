/**
 * Stock for the fridge's tests: one item builder, days counted from a fixed today, and
 * batches with names that hold no digits (the screen must show none).
 */

import type { InventoryItem } from '@/types/inventory'

export const TODAY = new Date('2026-09-25T12:00:00')

export function inDays(days: number): string {
  const date = new Date(TODAY)
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

export const item = (overrides: Partial<InventoryItem> = {}): InventoryItem => ({
  id: 'item-milk',
  product_master_id: 'p1',
  product_name: 'Oat Milk',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: '🥛',
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 750,
  unit: 'dl',
  status: 'opened',
  purchase_date: '2026-09-20',
  expiry_date: inDays(20),
  expiry_source: 'calculated',
  opened_date: null,
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2026-09-20T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
  ...overrides,
})

const WORDS = [
  'Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel', 'India', 'Juliet',
  'Kilo', 'Lima', 'Mike', 'November', 'Oscar', 'Papa', 'Quebec', 'Romeo', 'Sierra', 'Tango',
  'Uniform', 'Victor', 'Whiskey', 'Xray', 'Yankee', 'Zulu',
]

/** A name with no digits in it, for the n-th item of a batch. */
export function nameFor(index: number): string {
  const word = WORDS[index % WORDS.length]
  const round = Math.floor(index / WORDS.length)
  return round === 0 ? word : `${word} ${WORDS[round % WORDS.length].toLowerCase()}`
}

/** `count` items of one kind, all keeping (blue), none going stale. */
export function many(count: number, overrides: Partial<InventoryItem> = {}): InventoryItem[] {
  return Array.from({ length: count }, (_, index) =>
    item({
      id: `${overrides.category ?? 'dairy'}-${overrides.location ?? 'x'}-${index}`,
      product_name: nameFor(index),
      expiry_date: inDays(40),
      ...overrides,
    })
  )
}

/** `count` items going stale, meat and veggies in turn. */
export function stale(count: number): InventoryItem[] {
  return Array.from({ length: count }, (_, index) =>
    item({
      id: `stale-${index}`,
      product_name: `Stale ${nameFor(index)}`,
      category: index % 2 ? 'meat' : 'produce',
      category_icon: index % 2 ? '🥩' : '🥬',
      expiry_date: inDays(1),
    })
  )
}
