/**
 * Local calendar dates for <input type="date"> (MVP-S3).
 */

import { addDaysISO, toISODate } from '../dates'

afterEach(() => jest.useRealTimers())

describe('toISODate', () => {
  it('uses the local calendar day, not UTC', () => {
    // 23:30 local time must stay on the same day whatever the timezone offset
    expect(toISODate(new Date(2026, 8, 14, 23, 30))).toBe('2026-09-14')
    expect(toISODate(new Date(2026, 0, 5, 0, 15))).toBe('2026-01-05')
  })
})

describe('addDaysISO', () => {
  it('adds days to today', () => {
    jest.useFakeTimers().setSystemTime(new Date(2026, 8, 14, 10, 0))
    expect(addDaysISO(0)).toBe('2026-09-14')
    expect(addDaysISO(10)).toBe('2026-09-24')
    expect(addDaysISO(180)).toBe('2027-03-13')
  })

  it('crosses month ends', () => {
    expect(addDaysISO(3, new Date(2026, 1, 27))).toBe('2026-03-02')
  })
})
