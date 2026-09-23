/**
 * Date Utilities Tests (TDD)
 * Testing date calculations and expiry urgency logic
 */

import {
  calculateDaysUntilExpiry,
  formatAgo,
  getExpiryUrgency,
  formatExpiryDate,
  getExpiryColor,
  NEUTRAL_EXPIRY_COLOR,
  type ExpiryUrgency,
} from '../dates'

describe('Date Utilities', () => {
  // Mock current date to control test environment
  const MOCK_NOW = new Date('2024-01-15T12:00:00Z')

  beforeEach(() => {
    jest.useFakeTimers()
    jest.setSystemTime(MOCK_NOW)
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  describe('calculateDaysUntilExpiry', () => {
    it('should return 0 for today', () => {
      expect(calculateDaysUntilExpiry('2024-01-15')).toBe(0)
    })

    it('should return 1 for tomorrow', () => {
      expect(calculateDaysUntilExpiry('2024-01-16')).toBe(1)
    })

    it('should return positive days for future dates', () => {
      expect(calculateDaysUntilExpiry('2024-01-20')).toBe(5)
      expect(calculateDaysUntilExpiry('2024-01-22')).toBe(7)
    })

    it('should return negative days for past dates', () => {
      expect(calculateDaysUntilExpiry('2024-01-14')).toBe(-1)
      expect(calculateDaysUntilExpiry('2024-01-10')).toBe(-5)
    })

    it('should handle dates further in the future', () => {
      expect(calculateDaysUntilExpiry('2024-02-15')).toBe(31)
    })

    it('should handle ISO datetime strings', () => {
      expect(calculateDaysUntilExpiry('2024-01-16T10:00:00Z')).toBe(1)
    })

    it('should handle dates with time zones', () => {
      // Should calculate based on date only, ignoring time
      expect(calculateDaysUntilExpiry('2024-01-15T23:59:59Z')).toBe(0)
      expect(calculateDaysUntilExpiry('2024-01-16T00:00:01Z')).toBe(1)
    })
  })

  describe('getExpiryUrgency', () => {
    it('should return "expired" for past dates', () => {
      expect(getExpiryUrgency('2024-01-14')).toBe('expired')
      expect(getExpiryUrgency('2024-01-10')).toBe('expired')
      expect(getExpiryUrgency('2024-01-01')).toBe('expired')
    })

    it('should return "today" for current date', () => {
      expect(getExpiryUrgency('2024-01-15')).toBe('today')
    })

    it('should return "tomorrow" for next day', () => {
      expect(getExpiryUrgency('2024-01-16')).toBe('tomorrow')
    })

    it('should return "soon" for 2-3 days away', () => {
      expect(getExpiryUrgency('2024-01-17')).toBe('soon')
      expect(getExpiryUrgency('2024-01-18')).toBe('soon')
    })

    it('should return "fresh" for 4+ days away', () => {
      expect(getExpiryUrgency('2024-01-19')).toBe('fresh')
      expect(getExpiryUrgency('2024-01-20')).toBe('fresh')
      expect(getExpiryUrgency('2024-01-22')).toBe('fresh')
      expect(getExpiryUrgency('2024-02-15')).toBe('fresh')
    })

    it('should handle ISO datetime strings', () => {
      expect(getExpiryUrgency('2024-01-15T23:59:59Z')).toBe('today')
      expect(getExpiryUrgency('2024-01-16T00:00:01Z')).toBe('tomorrow')
    })
  })

  describe('formatExpiryDate', () => {
    it('says how long ago a past date was', () => {
      // Every past date used to read the one word "Expired", so yesterday's yoghurt and last
      // June's mince were indistinguishable on a display where they pile up.
      expect(formatExpiryDate('2024-01-14')).toBe('Yesterday')
      expect(formatExpiryDate('2024-01-10')).toBe('5 days ago')
      expect(formatExpiryDate('2023-12-25')).toBe('3 weeks ago')
    })

    it('should return "Today" for current date', () => {
      expect(formatExpiryDate('2024-01-15')).toBe('Today')
    })

    it('should return "Tomorrow" for next day', () => {
      expect(formatExpiryDate('2024-01-16')).toBe('Tomorrow')
    })

    it('should return "2 days" for day after tomorrow', () => {
      expect(formatExpiryDate('2024-01-17')).toBe('2 days')
    })

    it('should return "X days" for 3-6 days away', () => {
      expect(formatExpiryDate('2024-01-18')).toBe('3 days')
      expect(formatExpiryDate('2024-01-19')).toBe('4 days')
      expect(formatExpiryDate('2024-01-20')).toBe('5 days')
      expect(formatExpiryDate('2024-01-21')).toBe('6 days')
    })

    it('should return "1 week" for 7 days away', () => {
      expect(formatExpiryDate('2024-01-22')).toBe('1 week')
    })

    it('should return "X weeks" for 8-13 days away', () => {
      expect(formatExpiryDate('2024-01-23')).toBe('1 week')
      expect(formatExpiryDate('2024-01-29')).toBe('2 weeks')
    })

    it('should return "2 weeks" for 14+ days away', () => {
      expect(formatExpiryDate('2024-01-29')).toBe('2 weeks')
      expect(formatExpiryDate('2024-02-15')).toBe('4 weeks')
    })

    it('should handle ISO datetime strings', () => {
      expect(formatExpiryDate('2024-01-15T23:59:59Z')).toBe('Today')
      expect(formatExpiryDate('2024-01-16T00:00:01Z')).toBe('Tomorrow')
    })
  })

  describe('getExpiryColor', () => {
    it.each(['expired', 'today', 'tomorrow', 'soon', 'fresh'] as ExpiryUrgency[])(
      'gives %s a dark variant, so the badge is not bright on a dark kitchen screen',
      (urgency) => {
        const color = getExpiryColor(urgency)
        expect(color).toMatch(/dark:bg-/)
        expect(color).toMatch(/dark:text-/)
      }
    )

    // The lookup was unguarded, so an urgency arriving from untyped data put the literal string
    // "undefined" into the badge's class list (H04).
    it('falls back to neutral classes for an urgency it does not know', () => {
      const color = getExpiryColor('mouldy' as ExpiryUrgency)
      expect(color).toBe(NEUTRAL_EXPIRY_COLOR)
      expect(color).not.toContain('undefined')
    })

    it('should return red classes for "expired"', () => {
      const color = getExpiryColor('expired')
      expect(color).toContain('red')
      expect(color).toContain('bg-')
      expect(color).toContain('text-')
    })

    it('should return orange classes for "today"', () => {
      const color = getExpiryColor('today')
      expect(color).toContain('orange')
      expect(color).toContain('bg-')
      expect(color).toContain('text-')
    })

    it('should return orange classes for "tomorrow"', () => {
      const color = getExpiryColor('tomorrow')
      expect(color).toContain('orange')
      expect(color).toContain('bg-')
      expect(color).toContain('text-')
    })

    it('should return yellow classes for "soon"', () => {
      const color = getExpiryColor('soon')
      expect(color).toContain('yellow')
      expect(color).toContain('bg-')
      expect(color).toContain('text-')
    })

    it('should return green classes for "fresh"', () => {
      const color = getExpiryColor('fresh')
      expect(color).toContain('green')
      expect(color).toContain('bg-')
      expect(color).toContain('text-')
    })

    it('should return consistent format for all urgency levels', () => {
      const urgencies: ExpiryUrgency[] = ['expired', 'today', 'tomorrow', 'soon', 'fresh']

      urgencies.forEach(urgency => {
        const color = getExpiryColor(urgency)
        expect(color).toBeTruthy()
        expect(color).toMatch(/bg-\w+-\d+/)
        expect(color).toMatch(/text-\w+-\d+/)
      })
    })
  })

  describe('Integration tests', () => {
    it('should work together for expired item', () => {
      const expiryDate = '2024-01-10'
      const days = calculateDaysUntilExpiry(expiryDate)
      const urgency = getExpiryUrgency(expiryDate)
      const formatted = formatExpiryDate(expiryDate)
      const color = getExpiryColor(urgency)

      expect(days).toBeLessThan(0)
      expect(urgency).toBe('expired')
      expect(formatted).toBe('5 days ago')
      expect(color).toContain('red')
    })

    it('should work together for item expiring today', () => {
      const expiryDate = '2024-01-15'
      const days = calculateDaysUntilExpiry(expiryDate)
      const urgency = getExpiryUrgency(expiryDate)
      const formatted = formatExpiryDate(expiryDate)
      const color = getExpiryColor(urgency)

      expect(days).toBe(0)
      expect(urgency).toBe('today')
      expect(formatted).toBe('Today')
      expect(color).toContain('orange')
    })

    it('should work together for fresh item', () => {
      const expiryDate = '2024-01-20'
      const days = calculateDaysUntilExpiry(expiryDate)
      const urgency = getExpiryUrgency(expiryDate)
      const formatted = formatExpiryDate(expiryDate)
      const color = getExpiryColor(urgency)

      expect(days).toBe(5)
      expect(urgency).toBe('fresh')
      expect(formatted).toBe('5 days')
      expect(color).toContain('green')
    })
  })
})

describe('formatAgo: how old the thing on screen is', () => {
  const MOCK_NOW = new Date('2024-01-15T12:00:00Z')

  beforeEach(() => {
    jest.useFakeTimers()
    jest.setSystemTime(MOCK_NOW)
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  it.each([
    [0, 'just now'],
    [30_000, 'just now'],
    [60_000, '1 minute ago'],
    [4 * 60_000, '4 minutes ago'],
    [60 * 60_000, '1 hour ago'],
    [5 * 60 * 60_000, '5 hours ago'],
  ])('reads %i ms back as "%s"', (ago, expected) => {
    expect(formatAgo(MOCK_NOW.getTime() - ago)).toBe(expected)
  })

  it('stops counting hours at a day and gives the date instead', () => {
    // "37 hours ago" is a number nobody converts; a wall display should say the day.
    expect(formatAgo(new Date('2024-01-13T23:00:00Z').getTime())).toBe('13 January')
  })

  it('takes an ISO string as readily as a timestamp', () => {
    expect(formatAgo('2024-01-15T11:56:00Z')).toBe('4 minutes ago')
  })

  it('does not count into the future when a clock disagrees', () => {
    expect(formatAgo(MOCK_NOW.getTime() + 60_000)).toBe('just now')
  })
})
