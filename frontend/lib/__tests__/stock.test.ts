import { buildStockView, compareStock, EXPIRING_SOON_DAYS, isInactive } from '../stock'
import type { InventoryItem, InventoryLocation } from '@/types/inventory'

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
    unit: 'ml',
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

  describe('buildStockView', () => {
    it('pins expired, today, tomorrow and up to three days out', () => {
      expect(EXPIRING_SOON_DAYS).toBe(3)
      const expired = makeItem({ expiry_date: dateIn(-2) })
      const today = makeItem({ expiry_date: dateIn(0) })
      const tomorrow = makeItem({ expiry_date: dateIn(1) })
      const threeDays = makeItem({ expiry_date: dateIn(3) })
      const fourDays = makeItem({ expiry_date: dateIn(4) })

      const view = buildStockView([fourDays, threeDays, tomorrow, today, expired])

      expect(ids(view.expiringSoon)).toEqual([expired.id, today.id, tomorrow.id, threeDays.id])
      expect(view.groups).toHaveLength(1)
      expect(ids(view.groups[0].items)).toEqual([fourDays.id])
    })

    it('never lists a pinned item in its location group', () => {
      const pinned = makeItem({ expiry_date: dateIn(1), location: 'pantry' })
      const view = buildStockView([pinned])

      expect(ids(view.expiringSoon)).toEqual([pinned.id])
      expect(view.groups).toEqual([])
    })

    it('groups by location in a fixed order with labels and omits empty groups', () => {
      const pantry = makeItem({ location: 'pantry' })
      const fridge = makeItem({ location: 'main_fridge' })

      const view = buildStockView([pantry, fridge])

      expect(view.groups.map((g) => [g.key, g.label, g.items.length])).toEqual([
        ['main_fridge', 'Fridge', 1],
        ['pantry', 'Pantry', 1],
      ])
    })

    it('puts unknown locations in an Other group after the known ones', () => {
      const garage = makeItem({ location: 'garage' as InventoryLocation })
      const freezer = makeItem({ location: 'freezer' })

      const view = buildStockView([garage, freezer])

      expect(view.groups.map((g) => [g.key, g.label])).toEqual([
        ['freezer', 'Freezer'],
        ['other', 'Other'],
      ])
      expect(ids(view.groups[1].items)).toEqual([garage.id])
    })

    it('sorts items inside every group', () => {
      const late = makeItem({ expiry_date: dateIn(20) })
      const early = makeItem({ expiry_date: dateIn(10) })

      expect(ids(buildStockView([late, early]).groups[0].items)).toEqual([early.id, late.id])
    })

    it('hides empty and discarded items by default', () => {
      const active = makeItem()
      const empty = makeItem({ status: 'empty', current_quantity: 0 })
      const discarded = makeItem({ status: 'discarded', expiry_date: dateIn(1) })

      const view = buildStockView([active, empty, discarded])

      expect(view.expiringSoon).toEqual([])
      expect(ids(view.groups[0].items)).toEqual([active.id])
    })

    it('shows inactive items when asked', () => {
      const empty = makeItem({ status: 'empty', current_quantity: 0 })
      expect(ids(buildStockView([empty], { includeInactive: true }).groups[0].items)).toEqual([
        empty.id,
      ])
    })

    it('does not mutate the input', () => {
      const late = makeItem({ expiry_date: dateIn(20) })
      const early = makeItem({ expiry_date: dateIn(10) })
      const input = [late, early]

      buildStockView(input)

      expect(ids(input)).toEqual([late.id, early.id])
    })
  })
})
