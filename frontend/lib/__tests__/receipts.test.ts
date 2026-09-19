/**
 * How a receipt describes itself (Q9, Q10).
 *
 * Both of these exist because a receipt can be wrong in a way that looks fine. A
 * `heuristic` read reports `completed` with no categories and no estimates, and a receipt
 * from three months ago adds a shelf of already-expired food without a word.
 */

import { isStale, readMethod, receiptAgeDays, STALE_AFTER_DAYS } from '../receipts'

describe('readMethod', () => {
  it('names a model read so a good read is not silence', () => {
    // Before Q9 only `heuristic` said anything, so "the model ran" and "nobody looked"
    // were the same empty space on screen.
    expect(readMethod({ extraction_method: 'text' })).toEqual({
      label: 'read by the model',
      ok: true,
    })
    expect(readMethod({ extraction_method: 'vision' })?.ok).toBe(true)
  })

  it('flags a read the model never touched', () => {
    expect(readMethod({ extraction_method: 'heuristic' })).toEqual({
      label: 'read without the model',
      ok: false,
    })
  })

  it('says nothing about a receipt that has not been read', () => {
    expect(readMethod({ extraction_method: null })).toBeNull()
  })
})

describe('receiptAgeDays', () => {
  const today = new Date(2026, 8, 19) // 19 September 2026, local midnight

  it('counts whole days from the receipt date', () => {
    expect(receiptAgeDays({ purchase_date: '2026-09-19' }, today)).toBe(0)
    expect(receiptAgeDays({ purchase_date: '2026-09-18' }, today)).toBe(1)
    expect(receiptAgeDays({ purchase_date: '2026-06-09' }, today)).toBe(102)
  })

  it('has no age without a date, and none for an unreadable one', () => {
    expect(receiptAgeDays({ purchase_date: null }, today)).toBeNull()
    expect(receiptAgeDays({ purchase_date: 'not a date' }, today)).toBeNull()
  })

  it('is not thrown off by daylight saving', () => {
    // Finland puts its clocks forward on the last Sunday of March, so subtracting
    // wall-clock times across it gives 22.958 days and floors to 22. Both directions,
    // because only one of them loses the day - and in CI's UTC neither does, which is
    // exactly why this is asserted on calendar dates rather than on elapsed time.
    expect(receiptAgeDays({ purchase_date: '2026-03-20' }, new Date(2026, 3, 12))).toBe(23)
    expect(receiptAgeDays({ purchase_date: '2026-10-23' }, new Date(2026, 10, 15))).toBe(23)
  })
})

describe('isStale', () => {
  const today = new Date(2026, 8, 19)

  it('leaves a fresh receipt alone', () => {
    expect(isStale({ purchase_date: '2026-09-19' }, today)).toBe(false)
    expect(isStale({ purchase_date: '2026-09-05' }, today)).toBe(false) // exactly 14 days
  })

  it('warns once a receipt is older than a fortnight', () => {
    expect(isStale({ purchase_date: '2026-09-04' }, today)).toBe(true)
    expect(isStale({ purchase_date: '2026-06-09' }, today)).toBe(true)
  })

  it('cannot warn about a receipt whose date was never read', () => {
    // `receiptDate` renders "date not read" for these, and expiry falls back elsewhere.
    expect(isStale({ purchase_date: null }, today)).toBe(false)
  })

  it('a receipt dated in the future is not stale', () => {
    expect(isStale({ purchase_date: '2026-09-25' }, today)).toBe(false)
    expect(STALE_AFTER_DAYS).toBe(14)
  })
})
