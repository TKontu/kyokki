/**
 * The fridge's areas (V3): which area an item lives in, and what the going-stale shelf holds.
 */

import { AREAS, areaOf, areaTiles, buildFridgeView } from '../fridge'
import type { InventoryItem } from '@/types/inventory'

const TODAY = new Date('2026-09-25T12:00:00')

function inDays(days: number): string {
  const date = new Date(TODAY)
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

const item = (overrides: Partial<InventoryItem> = {}): InventoryItem => ({
  id: 'i1',
  product_master_id: 'p1',
  product_name: 'Milk',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: '🥛',
  receipt_id: null,
  initial_quantity: 10,
  current_quantity: 10,
  unit: 'dl',
  status: 'sealed',
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

// Mirrors backend/app/db/seed_categories.py: every seeded category needs an area.
const SEEDED = [
  'meat', 'fish', 'dairy', 'cheese', 'produce', 'fruits', 'bread',
  'ready_meals', 'frozen', 'pantry', 'beverages', 'condiments', 'snacks',
]

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(TODAY)
})
afterEach(() => jest.useRealTimers())

describe('areaOf', () => {
  it('files an item by its category', () => {
    expect(areaOf(item({ category: 'meat' }))).toBe('meat')
    expect(areaOf(item({ category: 'fish' }))).toBe('meat')
    expect(areaOf(item({ category: 'cheese' }))).toBe('dairy')
    expect(areaOf(item({ category: 'produce' }))).toBe('veggies')
    expect(areaOf(item({ category: 'condiments' }))).toBe('pantry')
  })

  it('puts anything in the freezer in the freezer, whatever it is', () => {
    expect(areaOf(item({ category: 'meat', location: 'freezer' }))).toBe('freezer')
  })

  it('puts frozen food in the freezer even when the location says otherwise', () => {
    expect(areaOf(item({ category: 'frozen', location: 'main_fridge' }))).toBe('freezer')
  })

  it('files an unknown category under Other', () => {
    expect(areaOf(item({ category: 'household' }))).toBe('other')
    expect(areaOf(item({ category: '' }))).toBe('other')
  })

  it.each(SEEDED)('has an area for the seeded category %s', (category) => {
    expect(areaOf(item({ category }))).not.toBe('other')
  })

  it('lists the areas in fridge order', () => {
    expect(AREAS.map((a) => a.id)).toEqual([
      'meat', 'veggies', 'fruits', 'dairy', 'bread', 'ready_meals', 'drinks', 'pantry',
      'freezer', 'other',
    ])
  })
})

describe('buildFridgeView', () => {
  it('puts what is going stale or due in a couple of days on the shelf', () => {
    const view = buildFridgeView([
      item({ id: 'stale', expiry_date: inDays(1) }),
      item({ id: 'soon', expiry_date: inDays(3) }),
      item({ id: 'week', expiry_date: inDays(6) }),
    ])

    expect(view.goingStale.map((i) => i.id)).toEqual(['stale', 'soon'])
  })

  it('still lists shelf items in their own area', () => {
    const view = buildFridgeView([item({ id: 'stale', expiry_date: inDays(1) })])

    expect(view.areas.find((a) => a.area.id === 'dairy')?.items.map((i) => i.id)).toEqual([
      'stale',
    ])
  })

  it('names what is already past its date, for the clear link', () => {
    const view = buildFridgeView([
      item({ id: 'past', expiry_date: inDays(-2) }),
      item({ id: 'today', expiry_date: inDays(0) }),
    ])

    expect(view.expired.map((i) => i.id)).toEqual(['past'])
  })

  it('leaves out what is used up or thrown away', () => {
    const view = buildFridgeView([
      item({ id: 'used', status: 'empty' }),
      item({ id: 'gone', status: 'discarded' }),
      item({ id: 'here' }),
    ])

    expect(view.areas.flatMap((a) => a.items.map((i) => i.id))).toEqual(['here'])
  })

  it('keeps every area, empty or not, so the fridge keeps its shape', () => {
    const view = buildFridgeView([])

    expect(view.areas.map((a) => a.area.id)).toEqual(AREAS.map((a) => a.id))
    expect(view.areas.every((a) => a.items.length === 0)).toBe(true)
  })

  it('sorts an area by expiry', () => {
    const view = buildFridgeView([
      item({ id: 'later', expiry_date: inDays(9) }),
      item({ id: 'first', expiry_date: inDays(5) }),
    ])

    expect(view.areas.find((a) => a.area.id === 'dairy')?.items.map((i) => i.id)).toEqual([
      'first',
      'later',
    ])
  })
})

describe('areaTiles (V4)', () => {
  it('lists what is here stalest first, then what was used up, latest first', () => {
    const tiles = areaTiles(
      [
        item({ id: 'later', expiry_date: inDays(9) }),
        item({ id: 'used-early', status: 'empty', consumed_at: '2026-09-25T07:00:00Z' }),
        item({ id: 'first', expiry_date: inDays(2) }),
        item({ id: 'used-late', status: 'empty', consumed_at: '2026-09-25T11:00:00Z' }),
      ],
      'dairy'
    )

    expect(tiles.map((i) => i.id)).toEqual(['first', 'later', 'used-late', 'used-early'])
  })

  it('keeps only the area asked for', () => {
    const tiles = areaTiles(
      [item({ id: 'milk' }), item({ id: 'steak', category: 'meat' })],
      'meat'
    )

    expect(tiles.map((i) => i.id)).toEqual(['steak'])
  })

  it('never offers back what was thrown away', () => {
    expect(areaTiles([item({ status: 'discarded' })], 'dairy')).toEqual([])
  })
})
