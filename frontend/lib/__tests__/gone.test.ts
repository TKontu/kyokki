/**
 * The Gone screen's own rules: what counts as gone, how far back it looks, and how the rows
 * are grouped so a day's waste reads as a day.
 */

import {
  GONE_ACTIONS,
  groupByDay,
  sinceFor,
  summaryLine,
  topWastingCategories,
  wasteRateLine,
  weekLabel,
  WINDOWS,
} from '../gone'
import type { CategoryWaste, ConsumptionLogEntry, WasteStats, WasteWeek } from '@/types/consumption'

const AT = new Date('2026-09-22T12:00:00Z')

const row = (overrides: Partial<ConsumptionLogEntry> = {}): ConsumptionLogEntry => ({
  id: 'l1',
  inventory_item_id: 'i1',
  item_status: 'discarded',
  product_master_id: 'p1',
  product_name: 'Minced Meat',
  unit: 'g',
  action: 'discard',
  quantity_consumed: 250,
  quantity_after: 0,
  logged_at: '2026-09-22T08:00:00Z',
  ...overrides,
})

describe('what the screen asks for', () => {
  it('shows what left the kitchen, not every helping', () => {
    // A part-used pack and a correction are history; neither is gone.
    expect(GONE_ACTIONS).toEqual(['discard', 'use_full'])
  })

  it('looks back 30 days by default, and can look further or less far', () => {
    expect(WINDOWS.map((w) => w.days)).toEqual([7, 30, null])
    expect(WINDOWS.find((w) => w.days === 30)?.default).toBe(true)
  })

  it('turns a window into the moment to read from', () => {
    expect(sinceFor(7, AT)).toBe('2026-09-15T12:00:00.000Z')
    expect(sinceFor(null, AT)).toBeUndefined()
  })
})

describe('groupByDay', () => {
  it('names today and yesterday, and dates the rest', () => {
    const groups = groupByDay(
      [
        row({ id: 'a', logged_at: '2026-09-22T08:00:00Z' }),
        row({ id: 'b', logged_at: '2026-09-21T19:00:00Z' }),
        row({ id: 'c', logged_at: '2026-09-21T08:00:00Z' }),
        row({ id: 'd', logged_at: '2026-09-02T08:00:00Z' }),
      ],
      AT
    )

    expect(groups.map((group) => group.label)).toEqual(['Today', 'Yesterday', '2 September'])
    expect(groups.map((group) => group.rows.map((r) => r.id))).toEqual([
      ['a'],
      ['b', 'c'],
      ['d'],
    ])
  })

  it('keeps the order it was given', () => {
    const groups = groupByDay([row({ id: 'newer' }), row({ id: 'older' })], AT)

    expect(groups).toHaveLength(1)
    expect(groups[0].rows.map((r) => r.id)).toEqual(['newer', 'older'])
  })

  it('has nothing to group when nothing happened', () => {
    expect(groupByDay([], AT)).toEqual([])
  })
})

describe('summaryLine', () => {
  it('counts items, not amounts (V2, presence not amounts)', () => {
    expect(summaryLine({ events: 8, totals: { g: 1400, pcs: 6 } })).toBe('8 items')
  })

  it('says one item as one item', () => {
    expect(summaryLine({ events: 1, totals: { dl: 10 } })).toBe('1 item')
  })

  it('says nothing happened rather than showing a zero', () => {
    expect(summaryLine(undefined)).toBe('none')
  })
})

const stats = (overrides: Partial<WasteStats> = {}): WasteStats => ({
  discarded: 3,
  finished: 7,
  total: 10,
  rate: 0.3,
  categories: [],
  ...overrides,
})

describe('wasteRateLine', () => {
  it('says what the window cost, as a percentage', () => {
    expect(wasteRateLine(stats())).toBe('You threw away 3 of 10 things (30 %)')
  })

  it('rounds to a whole percent', () => {
    expect(wasteRateLine(stats({ discarded: 1, finished: 2, total: 3, rate: 1 / 3 }))).toBe(
      'You threw away 1 of 3 things (33 %)'
    )
  })

  it('is a plain empty state rather than 0 % or NaN when nothing happened', () => {
    expect(wasteRateLine(stats({ discarded: 0, finished: 0, total: 0, rate: null }))).toBeNull()
    expect(wasteRateLine(undefined)).toBeNull()
  })
})

const category = (overrides: Partial<CategoryWaste> = {}): CategoryWaste => ({
  category: 'meat',
  display_name: 'Meat & Poultry',
  discarded: 3,
  finished: 0,
  total: 3,
  rate: 1,
  ...overrides,
})

describe('topWastingCategories', () => {
  it('takes the three worst - the service already sorts and thresholds them', () => {
    const categories = [
      category({ category: 'a' }),
      category({ category: 'b' }),
      category({ category: 'c' }),
      category({ category: 'd' }),
    ]

    expect(topWastingCategories(categories).map((c) => c.category)).toEqual(['a', 'b', 'c'])
  })

  it('is empty when nothing met the threshold', () => {
    expect(topWastingCategories([])).toEqual([])
  })
})

describe('weekLabel', () => {
  it('reads a week_start date as a short label', () => {
    expect(weekLabel({ week_start: '2026-01-12' } as WasteWeek)).toBe('12 Jan')
  })
})
