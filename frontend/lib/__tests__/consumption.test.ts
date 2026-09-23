import {
  applyConsume,
  cardActions,
  consumptionOptions,
  formatQuantity,
  isCountable,
  roundQuantity,
} from '../consumption'
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
    it('treats only pcs as countable', () => {
      expect(isCountable('pcs')).toBe(true)
      expect(isCountable('unit')).toBe(false) // legacy unit; migrated to pcs in MVP-U1
      expect(isCountable('dl')).toBe(false)
      expect(isCountable('g')).toBe(false)
    })
  })

  describe('proportional options', () => {
    it('labels each fraction with the amount it actually takes', () => {
      expect(consumptionOptions(makeItem()).map((o) => o.label)).toEqual([
        '¼ · 250 dl',
        '½ · 500 dl',
        '¾ · 750 dl',
        'Done',
      ])
    })

    it('computes a quarter of 1000 dl as 250 dl', () => {
      expect(byKey(makeItem()).quarter.amount).toBe(250)
      expect(byKey(makeItem()).half.amount).toBe(500)
      expect(byKey(makeItem()).threeQuarters.amount).toBe(750)
    })

    it('drops fractions that would finish the item', () => {
      // At 100 dl left of 1000, a quarter, a half and three quarters are all "everything"
      const options = consumptionOptions(makeItem({ current_quantity: 100 }))
      expect(options.map((o) => o.label)).toEqual(['Done'])
      expect(options[0].amount).toBe(100)
    })

    it('uses the whole remaining quantity for done', () => {
      expect(byKey(makeItem({ current_quantity: 420 })).done.amount).toBe(420)
    })

    it('rounds fractional amounts', () => {
      expect(byKey(makeItem({ initial_quantity: 333, current_quantity: 333 })).quarter.amount).toBe(
        83.25
      )
    })

    it('marks nothing primary when there are fractions to choose between', () => {
      expect(consumptionOptions(makeItem()).some((o) => o.primary)).toBe(false)
    })
  })

  describe('countable options', () => {
    it('leads with eating one, then smaller counts, then all of them', () => {
      const item = makeItem({ unit: 'pcs', initial_quantity: 13, current_quantity: 13 })
      const options = consumptionOptions(item)

      expect(options.map((o) => o.label)).toEqual(['1', '2', '3', 'All 13'])
      expect(options.map((o) => o.amount)).toEqual([1, 2, 3, 13])
      expect(options.every((o) => !o.disabled)).toBe(true)
    })

    it('makes eating one the primary act', () => {
      const options = byKey(makeItem({ unit: 'pcs', initial_quantity: 13, current_quantity: 13 }))
      expect(options['count-1'].primary).toBe(true)
      expect(options['count-2'].primary).toBe(false)
      expect(options.done.primary).toBe(false)
    })

    it('never offers a count that would finish the item', () => {
      // 3 of 3 is not "three", it is "all of them"
      const options = consumptionOptions(
        makeItem({ unit: 'pcs', initial_quantity: 6, current_quantity: 3 })
      )

      expect(options.map((o) => o.label)).toEqual(['1', '2', 'All 3'])
      expect(options.every((o) => !o.disabled)).toBe(true)
    })

    it('offers only finishing it when one is left', () => {
      const options = consumptionOptions(
        makeItem({ unit: 'pcs', initial_quantity: 6, current_quantity: 1 })
      )

      expect(options.map((o) => o.label)).toEqual(['All 1'])
      expect(options[0].primary).toBe(true)
      expect(options[0].amount).toBe(1)
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

describe('cardActions: what one tap on the card does', () => {
  it('takes one piece of something counted, and offers the rest as "All"', () => {
    const { step, finish } = cardActions(
      makeItem({ unit: 'pcs', initial_quantity: 6, current_quantity: 4 })
    )

    expect(step).toMatchObject({ amount: 1, label: '−1' })
    expect(finish).toMatchObject({ amount: 4, label: 'All 4' })
  })

  it('takes a quarter of the pack of something measured, labelled with the amount', () => {
    const { step, finish } = cardActions(
      makeItem({ unit: 'dl', initial_quantity: 10, current_quantity: 7.5 })
    )

    expect(step).toMatchObject({ amount: 2.5, label: '−¼ · 2.5 dl' })
    expect(finish).toMatchObject({ amount: 7.5, label: 'Done' })
  })

  it('makes finishing the big button when a step would take all of it anyway', () => {
    const counted = cardActions(makeItem({ unit: 'pcs', initial_quantity: 6, current_quantity: 1 }))
    const measured = cardActions(
      makeItem({ unit: 'dl', initial_quantity: 10, current_quantity: 2 })
    )

    expect(counted.step).toMatchObject({ key: 'done', amount: 1, label: 'All 1' })
    expect(counted.finish).toBeUndefined()
    expect(measured.step).toMatchObject({ key: 'done', amount: 2 })
    expect(measured.finish).toBeUndefined()
  })

  it('offers nothing to consume on something already gone', () => {
    const { step, finish } = cardActions(makeItem({ status: 'empty', current_quantity: 0 }))

    expect(step).toBeUndefined()
    expect(finish).toBeUndefined()
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
