/**
 * Staleness tiers (V1, operator ask 2026-09-24): the colour a tile wears instead of a number.
 *
 * Red is going stale, orange a couple of days, green about a week, blue longer, grey used up.
 */

import { STALENESS, stalenessOf } from '../staleness'

const TODAY = new Date('2026-09-25T12:00:00')

function inDays(days: number): string {
  const date = new Date(TODAY)
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

const item = (days: number, status = 'opened') => ({ expiry_date: inDays(days), status })

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(TODAY)
})
afterEach(() => jest.useRealTimers())

describe('stalenessOf', () => {
  it.each([
    [-5, 'stale'],
    [-1, 'stale'],
    [0, 'stale'],
    [1, 'stale'],
    [2, 'soon'],
    [3, 'soon'],
    [4, 'week'],
    [7, 'week'],
    [8, 'later'],
    [400, 'later'],
  ])('%i days left is %s', (days, tier) => {
    expect(stalenessOf(item(days))).toBe(tier)
  })

  it('an item used up is consumed, whatever its date', () => {
    expect(stalenessOf(item(-3, 'empty'))).toBe('consumed')
    expect(stalenessOf(item(30, 'empty'))).toBe('consumed')
  })
})

describe('STALENESS', () => {
  it('names every tier in words, so colour is never the only signal', () => {
    expect(Object.fromEntries(Object.entries(STALENESS).map(([k, v]) => [k, v.label]))).toEqual({
      stale: 'going stale',
      soon: 'a couple of days',
      week: 'about a week',
      later: 'keeps',
      consumed: 'used up',
    })
  })

  it('gives each tier its own colour', () => {
    expect(STALENESS.stale.tile).toMatch(/red/)
    expect(STALENESS.soon.tile).toMatch(/orange/)
    expect(STALENESS.week.tile).toMatch(/green/)
    expect(STALENESS.later.tile).toMatch(/blue/)
    expect(STALENESS.consumed.tile).toMatch(/gray/)
  })
})
