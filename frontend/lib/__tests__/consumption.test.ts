import {
  applyConsume,
  consumptionOptions,
  formatQuantity,
  isCountable,
  roundQuantity,
} from '../consumption'
import type { InventoryItem } from '@/types/inventory'

function makeItem(overrides: Partial<InventoryItem> = {}): InventoryItem {
  return {
    id: 'item-1',
    product_master_id: 'prod-1',
    product_name: 'Oat Milk',
    category: 'dairy',
    category_name: 'Dairy & Eggs',
    category_icon: null,
    receipt_id: null,
    initial_quantity: 1000,
    current_quantity: 1000,
    unit: 'ml',
    status: 'sealed',
    purchase_date: '2024-01-01',
    expiry_date: '2024-03-01',
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

function byKey(item: InventoryItem) {
  return Object.fromEntries(consumptionOptions(item).map((o) => [o.key, o]))
}

describe('consumption', () => {
  describe('roundQuantity and formatQuantity', () => {
    it('rounds to two decimals like the Numeric(10, 2) column', () => {
      expect(roundQuantity(83.255)).toBe(83.26)
      expect(roundQuantity(0.1 + 0.2)).toBe(0.3)
    })

    it('formats whole numbers without decimals and trims trailing zeros', () => {
      expect(formatQuantity(250)).toBe('250')
      expect(formatQuantity(83.25)).toBe('83.25')
      expect(formatQuantity(1.5)).toBe('1.5')
    })
  })

  describe('isCountable', () => {
    it('treats pcs and unit as countable', () => {
      expect(isCountable('pcs')).toBe(true)
      expect(isCountable('unit')).toBe(true)
      expect(isCountable('ml')).toBe(false)
      expect(isCountable('g')).toBe(false)
    })
  })

  describe('proportional options', () => {
    it('offers quarter, half, three quarters and done', () => {
      expect(consumptionOptions(makeItem()).map((o) => o.label)).toEqual(['¼', '½', '¾', 'Done'])
    })

    it('computes a quarter of 1000 ml as 250 ml', () => {
      expect(byKey(makeItem()).quarter.amount).toBe(250)
      expect(byKey(makeItem()).half.amount).toBe(500)
      expect(byKey(makeItem()).threeQuarters.amount).toBe(750)
    })

    it('caps fractions at what is left', () => {
      const options = byKey(makeItem({ current_quantity: 100 }))
      expect(options.quarter.amount).toBe(100)
      expect(options.half.amount).toBe(100)
      expect(options.half.disabled).toBe(false)
    })

    it('uses the whole remaining quantity for done', () => {
      expect(byKey(makeItem({ current_quantity: 420 })).done.amount).toBe(420)
    })

    it('rounds fractional amounts', () => {
      expect(byKey(makeItem({ initial_quantity: 333, current_quantity: 333 })).quarter.amount).toBe(
        83.25
      )
    })
  })

  describe('countable options', () => {
    it('offers -1, -2, -3 and done for pieces', () => {
      const item = makeItem({ unit: 'pcs', initial_quantity: 6, current_quantity: 6 })
      const options = consumptionOptions(item)
      expect(options.map((o) => o.label)).toEqual(['−1', '−2', '−3', 'Done'])
      expect(options.map((o) => o.amount)).toEqual([1, 2, 3, 6])
      expect(options.every((o) => !o.disabled)).toBe(true)
    })

    it('disables counts that are not less than what is left', () => {
      const options = byKey(makeItem({ unit: 'pcs', initial_quantity: 6, current_quantity: 2 }))
      expect(options.one.disabled).toBe(false)
      expect(options.two.disabled).toBe(true)
      expect(options.three.disabled).toBe(true)
      expect(options.done.disabled).toBe(false)
      expect(options.done.amount).toBe(2)
    })
  })

  describe('inactive items', () => {
    it.each(['empty', 'discarded'] as const)('disables every option for %s items', (status) => {
      const options = consumptionOptions(makeItem({ status, current_quantity: 0 }))
      expect(options.every((o) => o.disabled)).toBe(true)
    })

    it('disables every option when nothing is left', () => {
      const options = consumptionOptions(makeItem({ status: 'opened', current_quantity: 0 }))
      expect(options.every((o) => o.disabled)).toBe(true)
    })
  })

  describe('applyConsume', () => {
    beforeEach(() => {
      jest.useFakeTimers()
      jest.setSystemTime(new Date('2024-02-01T12:00:00Z'))
    })

    afterEach(() => {
      jest.useRealTimers()
    })

    it('opens a sealed item and stamps the opened date', () => {
      const updated = applyConsume(makeItem(), 100)
      expect(updated.current_quantity).toBe(900)
      expect(updated.status).toBe('opened')
      expect(updated.opened_date).toBe('2024-02-01')
    })

    it('keeps an existing opened date', () => {
      const updated = applyConsume(
        makeItem({ status: 'opened', current_quantity: 900, opened_date: '2024-01-20' }),
        100
      )
      expect(updated.opened_date).toBe('2024-01-20')
    })

    it('marks an item partial below 75 percent', () => {
      expect(applyConsume(makeItem(), 500).status).toBe('partial')
    })

    it('marks an item empty at zero', () => {
      const updated = applyConsume(makeItem({ current_quantity: 250 }), 250)
      expect(updated.current_quantity).toBe(0)
      expect(updated.status).toBe('empty')
    })

    it('never goes below zero and rounds the result', () => {
      expect(applyConsume(makeItem({ current_quantity: 100 }), 150).current_quantity).toBe(0)
      expect(applyConsume(makeItem({ current_quantity: 100.3 }), 0.1).current_quantity).toBe(100.2)
    })

    it('does not mutate the original item', () => {
      const item = makeItem()
      applyConsume(item, 100)
      expect(item.current_quantity).toBe(1000)
    })
  })
})
