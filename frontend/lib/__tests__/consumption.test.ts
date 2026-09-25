import { applyConsume, roundQuantity } from '../consumption'
import type { InventoryItem } from '@/types/inventory'
import contract from '../../../contracts/status-transitions.json'

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
    unit: 'dl',
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
    opened_shelf_life_days: null,
    avg_piece_grams: null,
    ...overrides,
  }
}

describe('consumption', () => {
  describe('roundQuantity', () => {
    it('rounds to two decimals like the Numeric(10, 2) column', () => {
      expect(roundQuantity(83.255)).toBe(83.26)
      expect(roundQuantity(0.1 + 0.2)).toBe(0.3)
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

  describe('the shared status table', () => {
    // contracts/status-transitions.json is the one copy of the rule. The server answers to it
    // in backend/tests/crud/test_quantity_status.py; this is the other half, and the reason
    // the optimistic label on a Consume tap matches what comes back a round trip later.
    const consumeCases = contract.cases.filter(
      (c: { event: string; serverOnly?: boolean }) => c.event === 'consume' && !c.serverOnly
    )

    it.each(consumeCases)('$name', (testCase) => {
      const { from, initial, remaining, opened, to } = testCase as {
        from: string
        initial: number
        remaining: number
        opened: boolean
        to: string
      }
      const item = makeItem({
        status: from,
        initial_quantity: initial,
        current_quantity: initial,
        opened_date: opened ? '2024-01-20' : null,
      })

      expect(applyConsume(item, initial - remaining).status).toBe(to)
    })

    it('uses the same threshold the server does', () => {
      // 75 % exactly is `opened`; a hair under is `partial`.
      const atThreshold = makeItem({ initial_quantity: 100, current_quantity: 100 })
      expect(applyConsume(atThreshold, 100 * (1 - contract.partialThreshold)).status).toBe(
        'opened'
      )
      expect(applyConsume(atThreshold, 100 * (1 - contract.partialThreshold) + 1).status).toBe(
        'partial'
      )
    })
  })
  })
})

describe('applyConsume and the opened clock (Q5)', () => {
  // Mirrors backend/app/crud/inventory_item.py `_start_opened_clock`. The card used to show
  // the old expiry until the server answered, then jump - sometimes green to red (H25).
  beforeEach(() => {
    jest.useFakeTimers()
    jest.setSystemTime(new Date('2024-02-01T12:00:00Z'))
  })

  afterEach(() => jest.useRealTimers())

  it('brings the date forward when a pack is opened', () => {
    const sealed = makeItem({
      status: 'sealed',
      expiry_date: '2024-03-01',
      opened_shelf_life_days: 3,
    })

    expect(applyConsume(sealed, 250).expiry_date).toBe('2024-02-04')
  })

  it('never lengthens it: a jar opened the day before its date keeps that date', () => {
    const sealed = makeItem({
      status: 'sealed',
      expiry_date: '2024-02-02',
      opened_shelf_life_days: 14,
    })

    expect(applyConsume(sealed, 250).expiry_date).toBe('2024-02-02')
  })

  it('leaves loose produce alone, because taking one apple opens nothing', () => {
    const apples = makeItem({
      status: 'sealed',
      unit: 'pcs',
      initial_quantity: 13,
      current_quantity: 13,
      expiry_date: '2024-03-01',
      opened_shelf_life_days: 3,
      avg_piece_grams: 150,
    })

    expect(applyConsume(apples, 1).expiry_date).toBe('2024-03-01')
  })

  it('says nothing about the date when the product does not know how long it keeps', () => {
    const sealed = makeItem({ status: 'sealed', expiry_date: '2024-03-01' })

    expect(applyConsume(sealed, 250).expiry_date).toBe('2024-03-01')
  })

  it('leaves an already-opened pack on its clock', () => {
    const opened = makeItem({
      status: 'opened',
      opened_date: '2024-01-20',
      expiry_date: '2024-02-10',
      opened_shelf_life_days: 3,
    })

    expect(applyConsume(opened, 250).expiry_date).toBe('2024-02-10')
  })
})
