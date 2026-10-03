/**
 * How a receipt describes itself (Q9, Q10).
 *
 * Both of these exist because a receipt can be wrong in a way that looks fine. A
 * `heuristic` read reports `completed` with no categories and no estimates, and a receipt
 * from three months ago adds a shelf of already-expired food without a word.
 */

import { isStale, readMethod, receiptAgeDays, receiptDate, storeName, STALE_AFTER_DAYS } from '../receipts'

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

  describe('display language (Post-MVP frontier item 13, phase 3)', () => {
    it('reads English by default, unchanged', () => {
      expect(readMethod({ extraction_method: 'text' }, 'en')).toEqual({
        label: 'read by the model',
        ok: true,
      })
    })

    it('reads Finnish once the device has chosen it', () => {
      expect(readMethod({ extraction_method: 'text' }, 'fi')).toEqual({
        label: 'luettu mallilla',
        ok: true,
      })
      expect(readMethod({ extraction_method: 'vision' }, 'fi')).toEqual({
        label: 'luettu mallilla kuvasta',
        ok: true,
      })
      expect(readMethod({ extraction_method: 'heuristic' }, 'fi')).toEqual({
        label: 'luettu ilman mallia',
        ok: false,
      })
    })

    it('still says nothing about an unread receipt in Finnish', () => {
      expect(readMethod({ extraction_method: null }, 'fi')).toBeNull()
    })
  })
})

describe('storeName: display language (Post-MVP frontier item 13, phase 3)', () => {
  it('keeps a known chain name the same in both languages - a proper noun, not translated', () => {
    expect(storeName({ store_chain: 's-group' }, 'en')).toBe('S-group')
    expect(storeName({ store_chain: 's-group' }, 'fi')).toBe('S-group')
  })

  it('translates the fallback for a receipt with no chain read', () => {
    expect(storeName({ store_chain: null }, 'en')).toBe('Unknown store')
    expect(storeName({ store_chain: null }, 'fi')).toBe('Tuntematon kauppa')
  })
})

describe('receiptDate: display language (Post-MVP frontier item 13, phase 3)', () => {
  it('keeps the d.m.yyyy shape in both languages - already locale-neutral', () => {
    expect(receiptDate({ purchase_date: '2026-09-02' }, 'en')).toBe('2.9.2026')
    expect(receiptDate({ purchase_date: '2026-09-02' }, 'fi')).toBe('2.9.2026')
  })

  it('translates the fallback for a receipt with no date read', () => {
    expect(receiptDate({ purchase_date: null }, 'en')).toBe('date not read')
    expect(receiptDate({ purchase_date: null }, 'fi')).toBe('päivää ei luettu')
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
