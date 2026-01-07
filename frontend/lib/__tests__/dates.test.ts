/**
 * Date Utilities Tests (TDD)
 * Testing date calculations and expiry urgency logic
 */

import {
  calculateDaysUntilExpiry,
  getExpiryUrgency,
  formatExpiryDate,
  getExpiryColor,
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
    it('should return "Expired" for past dates', () => {
      expect(formatExpiryDate('2024-01-14')).toBe('Expired')
      expect(formatExpiryDate('2024-01-10')).toBe('Expired')
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
      expect(formatted).toBe('Expired')
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
