import {
  compareStock,
  isInactive,
  LOCATION_OPTIONS,
  locationOptions,
} from '../stock'
import type { InventoryItem } from '@/types/inventory'

// Fake "now" is 2024-02-01 local noon; expiry offsets are relative to that date.
const TODAY = '2024-02-01'

function dateIn(days: number): string {
  const d = new Date(2024, 1, 1 + days)
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}

let counter = 0

function makeItem(overrides: Partial<InventoryItem> = {}): InventoryItem {
  counter += 1
  return {
    id: `item-${String(counter).padStart(3, '0')}`,
    product_master_id: 'prod-1',
    product_name: `Product ${counter}`,
    category: 'dairy',
    category_name: 'Dairy & Eggs',
    category_icon: null,
    receipt_id: null,
    initial_quantity: 1000,
    current_quantity: 1000,
    unit: 'dl',
    status: 'sealed',
    purchase_date: TODAY,
    expiry_date: dateIn(30),
    expiry_source: 'calculated',
    opened_date: null,
    batch_number: null,
    location: 'main_fridge',
    notes: null,
    created_at: '2024-01-01T10:00:00Z',
    consumed_at: null,
    opened_shelf_life_days: null,
    avg_piece_grams: null,
    ...overrides,
  }
}

const ids = (items: InventoryItem[]) => items.map((item) => item.id)

beforeEach(() => {
  counter = 0
  jest.useFakeTimers()
  jest.setSystemTime(new Date(2024, 1, 1, 12, 0, 0))
})

afterEach(() => {
  jest.useRealTimers()
})

describe('stock', () => {
  // An unknown location used to leave every radio unchecked, so the form looked like it had no
  // answer and an edit sheet's diff never saw a change (H04).
  describe('locationOptions', () => {
    it('offers the three known locations and nothing else', () => {
      expect(locationOptions('freezer')).toBe(LOCATION_OPTIONS)
      expect(locationOptions()).toBe(LOCATION_OPTIONS)
      expect(locationOptions('')).toBe(LOCATION_OPTIONS)
    })

    it('adds a location it does not know as its own option, labelled raw', () => {
      const options = locationOptions('cellar')
      expect(options).toHaveLength(LOCATION_OPTIONS.length + 1)
      expect(options[options.length - 1]).toEqual({ value: 'cellar', label: 'cellar' })
    })

    it('does not mutate the shared option list', () => {
      locationOptions('cellar')
      expect(LOCATION_OPTIONS.map((option) => option.value)).toEqual([
        'main_fridge',
        'freezer',
        'pantry',
      ])
    })
  })

  describe('compareStock', () => {
    it('sorts by expiry date ascending', () => {
      const late = makeItem({ expiry_date: dateIn(20) })
      const early = makeItem({ expiry_date: dateIn(10) })
      expect(ids([late, early].sort(compareStock))).toEqual([early.id, late.id])
    })

    it('breaks expiry ties by creation time', () => {
      const newer = makeItem({ expiry_date: dateIn(10), created_at: '2024-01-02T10:00:00Z' })
      const older = makeItem({ expiry_date: dateIn(10), created_at: '2024-01-01T10:00:00Z' })
      expect(ids([newer, older].sort(compareStock))).toEqual([older.id, newer.id])
    })

    it('breaks remaining ties by id so the order is total', () => {
      const b = makeItem({ id: 'b', expiry_date: dateIn(10) })
      const a = makeItem({ id: 'a', expiry_date: dateIn(10) })
      expect(ids([b, a].sort(compareStock))).toEqual(['a', 'b'])
      expect(ids([a, b].sort(compareStock))).toEqual(['a', 'b'])
    })
  })

  describe('isInactive', () => {
    it('is true only for empty and discarded items', () => {
      expect(isInactive(makeItem({ status: 'empty' }))).toBe(true)
      expect(isInactive(makeItem({ status: 'discarded' }))).toBe(true)
      expect(isInactive(makeItem({ status: 'partial' }))).toBe(false)
    })
  })
})
