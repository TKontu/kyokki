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
  windowLabel,
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

  describe('display language (review F1, round 2026-10-03-1)', () => {
    it('reads Tänään/Eilen in Finnish when asked, English by default', () => {
      const rows = [
        row({ id: 'a', logged_at: '2026-09-22T08:00:00Z' }),
        row({ id: 'b', logged_at: '2026-09-21T19:00:00Z' }),
        row({ id: 'd', logged_at: '2026-09-02T08:00:00Z' }),
      ]

      expect(groupByDay(rows, AT).map((g) => g.label)).toEqual([
        'Today',
        'Yesterday',
        '2 September',
      ])
      expect(groupByDay(rows, AT, 'en').map((g) => g.label)).toEqual([
        'Today',
        'Yesterday',
        '2 September',
      ])
      expect(groupByDay(rows, AT, 'fi').map((g) => g.label)).toEqual([
        'Tänään',
        'Eilen',
        '2. syyskuuta',
      ])
    })
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

  describe('display language (review F1, round 2026-10-03-1)', () => {
    it('reads in Finnish when asked, English by default', () => {
      expect(summaryLine({ events: 8, totals: {} })).toBe('8 items')
      expect(summaryLine({ events: 8, totals: {} }, 'en')).toBe('8 items')
      expect(summaryLine({ events: 8, totals: {} }, 'fi')).toBe('8 tuotetta')
      expect(summaryLine({ events: 1, totals: {} }, 'fi')).toBe('1 tuote')
      expect(summaryLine(undefined, 'fi')).toBe('ei mitään')
    })
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

  describe('display language (review F1, round 2026-10-03-1)', () => {
    it('reads in Finnish when asked, English by default', () => {
      expect(wasteRateLine(stats())).toBe('You threw away 3 of 10 things (30 %)')
      expect(wasteRateLine(stats(), 'en')).toBe('You threw away 3 of 10 things (30 %)')
      expect(wasteRateLine(stats(), 'fi')).toBe('Heitit pois 3/10 asiaa (30 %)')
    })

    it('still answers null for the empty state, in Finnish too', () => {
      expect(
        wasteRateLine(stats({ discarded: 0, finished: 0, total: 0, rate: null }), 'fi')
      ).toBeNull()
    })
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

  describe('display language (review F1, round 2026-10-03-1)', () => {
    it('reads in Finnish when asked, English by default', () => {
      const week = { week_start: '2026-01-12' } as WasteWeek
      expect(weekLabel(week)).toBe('12 Jan')
      expect(weekLabel(week, 'en')).toBe('12 Jan')
      expect(weekLabel(week, 'fi')).toBe('12.1.')
    })
  })
})

describe('windowLabel', () => {
  it('reads the window labels in Finnish when asked, English by default', () => {
    const sevenDays = WINDOWS.find((w) => w.days === 7)!
    const all = WINDOWS.find((w) => w.days === null)!
    expect(windowLabel(sevenDays)).toBe('7 days')
    expect(windowLabel(sevenDays, 'en')).toBe('7 days')
    expect(windowLabel(sevenDays, 'fi')).toBe('7 päivää')
    expect(windowLabel(all, 'fi')).toBe('Kaikki')
  })
})
