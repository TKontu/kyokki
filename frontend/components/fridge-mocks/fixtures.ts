/**
 * Sample stock for the fridge mocks (Q17-M), so a design can be judged on a homelab with an
 * empty fridge. About two dozen items across every area and every tier.
 *
 * Dates are found through `stalenessOf` rather than written as day counts, so the sample keeps
 * covering every tier when the thresholds move.
 */

import { stalenessOf, type Staleness } from '@/lib/staleness'
import type { InventoryItem } from '@/types/inventory'

type Tier = Exclude<Staleness, 'consumed'>

/** How far to look for a date in each tier, in days from today. */
const SEARCH_FROM = -3
const SEARCH_TO = 180

function isoInDays(days: number): string {
  const date = new Date()
  date.setHours(12, 0, 0, 0)
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

/**
 * An expiry date in a tier. `rank` picks among the tier's days: nought is its soonest, and a
 * higher rank a later one (clamped), so two items of a tier need not share a date.
 */
function expiryIn(tier: Tier, rank = 0): string {
  const days: number[] = []
  for (let day = SEARCH_FROM; day <= SEARCH_TO; day++) {
    if (stalenessOf({ expiry_date: isoInDays(day), status: 'sealed' }) === tier) days.push(day)
  }
  if (days.length === 0) return isoInDays(SEARCH_TO)
  return isoInDays(days[Math.min(rank, days.length - 1)])
}

const ICONS: Record<string, string> = {
  meat: '🥩',
  fish: '🐟',
  dairy: '🥛',
  cheese: '🧀',
  produce: '🥬',
  fruits: '🍎',
  bread: '🍞',
  ready_meals: '🍲',
  frozen: '🧊',
  pantry: '🥫',
  beverages: '🥤',
  condiments: '🍯',
  snacks: '🍿',
  household: '🧽',
}

type Sample = [name: string, category: string, tier: Tier, rank?: number, freezer?: boolean]

const SAMPLES: Sample[] = [
  ['Minced meat', 'meat', 'stale'],
  ['Salmon fillet', 'fish', 'soon'],
  ['Chicken thighs', 'meat', 'week', 2],
  ['Spinach', 'produce', 'stale', 1],
  ['Cucumber', 'produce', 'soon', 1],
  ['Carrots', 'produce', 'week', 3],
  ['Potatoes', 'produce', 'later', 20],
  ['Strawberries', 'fruits', 'stale', 2],
  ['Bananas', 'fruits', 'soon'],
  ['Apples', 'fruits', 'later', 10],
  ['Milk', 'dairy', 'week'],
  ['Yoghurt', 'dairy', 'soon', 1],
  ['Butter', 'dairy', 'later', 30],
  ['Emmental', 'cheese', 'later', 15],
  ['Rye bread', 'bread', 'soon'],
  ['Buns', 'bread', 'stale', 3],
  ['Lasagne', 'ready_meals', 'stale', 0],
  ['Pea soup', 'ready_meals', 'week', 1],
  ['Orange juice', 'beverages', 'week', 3],
  ['Sparkling water', 'beverages', 'later', 60],
  ['Pasta', 'pantry', 'later', 120],
  ['Ketchup', 'condiments', 'later', 90],
  ['Crisps', 'snacks', 'week', 2],
  ['Frozen peas', 'produce', 'later', 150, true],
  ['Ice cream', 'frozen', 'later', 100, true],
  ['Fish fingers', 'frozen', 'soon', 0, true],
  ['Dish sponges', 'household', 'later', 150],
]

export function fixtureItems(): InventoryItem[] {
  return SAMPLES.map(([name, category, tier, rank = 0, freezer = false], index) => ({
    id: `sample-${name.toLowerCase().replace(/\s+/g, '-')}`,
    product_master_id: `sample-product-${category}-${index}`,
    product_name: name,
    category,
    category_name: category,
    category_icon: ICONS[category] ?? null,
    receipt_id: null,
    initial_quantity: 1,
    current_quantity: 1,
    unit: 'pcs',
    status: 'sealed',
    purchase_date: isoInDays(-2),
    expiry_date: expiryIn(tier, rank),
    expiry_source: 'calculated',
    opened_date: null,
    batch_number: null,
    location: freezer ? 'freezer' : category === 'pantry' ? 'pantry' : 'main_fridge',
    notes: null,
    created_at: `${isoInDays(-2)}T10:00:00Z`,
    consumed_at: null,
    opened_shelf_life_days: null,
    avg_piece_grams: null,
  }))
}
