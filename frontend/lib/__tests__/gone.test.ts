/**
 * The Gone screen's own rules: what counts as gone, how far back it looks, and how the rows
 * are grouped so a day's waste reads as a day.
 */

import { GONE_ACTIONS, groupByDay, sinceFor, summaryLine, WINDOWS } from '../gone'
import type { ConsumptionLogEntry } from '@/types/consumption'

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
