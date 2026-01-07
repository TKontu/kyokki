/**
 * ExpiryBadge Component Tests (TDD)
 * Enhanced expiry badge using date utilities with icon indicators
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { ExpiryBadge } from '../ExpiryBadge'

describe('ExpiryBadge', () => {
  // Mock current date to control test environment
  const MOCK_NOW = new Date('2024-01-15T12:00:00Z')

  beforeEach(() => {
    jest.useFakeTimers()
    jest.setSystemTime(MOCK_NOW)
  })

  afterEach(() => {
    jest.useRealTimers()
  })

  describe('Basic rendering', () => {
    it('should render with expiry date', () => {
      render(<ExpiryBadge expiryDate="2024-01-20" />)
      expect(screen.getByText(/5 days/i)).toBeInTheDocument()
    })

    it('should render with custom className', () => {
      const { container } = render(
        <ExpiryBadge expiryDate="2024-01-20" className="custom-class" />
      )
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toContain('custom-class')
    })
  })

  describe('Expiry urgency levels', () => {
    it('should render "Expired" for past dates with warning icon', () => {
      render(<ExpiryBadge expiryDate="2024-01-10" />)
      expect(screen.getByText(/Expired/i)).toBeInTheDocument()
      expect(screen.getByText('⚠️')).toBeInTheDocument()
    })

    it('should render "Today" for current date with warning icon', () => {
      render(<ExpiryBadge expiryDate="2024-01-15" />)
      expect(screen.getByText(/Today/i)).toBeInTheDocument()
      expect(screen.getByText('⚠️')).toBeInTheDocument()
    })

    it('should render "Tomorrow" for next day', () => {
      render(<ExpiryBadge expiryDate="2024-01-16" />)
      expect(screen.getByText(/Tomorrow/i)).toBeInTheDocument()
    })

    it('should render "2 days" for soon expiry', () => {
      render(<ExpiryBadge expiryDate="2024-01-17" />)
      expect(screen.getByText(/2 days/i)).toBeInTheDocument()
    })

    it('should render "5 days" for fresh items', () => {
      render(<ExpiryBadge expiryDate="2024-01-20" />)
      expect(screen.getByText(/5 days/i)).toBeInTheDocument()
    })

    it('should render "1 week" for far future dates', () => {
      render(<ExpiryBadge expiryDate="2024-01-22" />)
      expect(screen.getByText(/1 week/i)).toBeInTheDocument()
    })
  })

  describe('Color styling based on urgency', () => {
    it('should apply red styling for expired items', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-10" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toContain('bg-red-100')
      expect(badge.className).toContain('text-red-800')
    })

    it('should apply orange styling for today', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-15" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toContain('bg-orange-100')
      expect(badge.className).toContain('text-orange-800')
    })

    it('should apply orange styling for tomorrow', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-16" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toContain('bg-orange-100')
      expect(badge.className).toContain('text-orange-800')
    })

    it('should apply yellow styling for soon (2-3 days)', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-17" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toContain('bg-yellow-100')
      expect(badge.className).toContain('text-yellow-800')
    })

    it('should apply green styling for fresh items (4+ days)', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-20" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toContain('bg-green-100')
      expect(badge.className).toContain('text-green-800')
    })
  })

  describe('Expiry source indicators', () => {
    it('should show calendar icon for scanned dates', () => {
      render(<ExpiryBadge expiryDate="2024-01-20" expirySource="scanned" />)
      expect(screen.getByText('📅')).toBeInTheDocument()
    })

    it('should not show calendar icon for calculated dates', () => {
      render(<ExpiryBadge expiryDate="2024-01-20" expirySource="calculated" />)
      expect(screen.queryByText('📅')).not.toBeInTheDocument()
    })

    it('should not show calendar icon for manual dates', () => {
      render(<ExpiryBadge expiryDate="2024-01-20" expirySource="manual" />)
      expect(screen.queryByText('📅')).not.toBeInTheDocument()
    })

    it('should not show calendar icon when no source specified', () => {
      render(<ExpiryBadge expiryDate="2024-01-20" />)
      expect(screen.queryByText('📅')).not.toBeInTheDocument()
    })

    it('should show both warning and calendar icons for expired scanned items', () => {
      render(<ExpiryBadge expiryDate="2024-01-10" expirySource="scanned" />)
      expect(screen.getByText('⚠️')).toBeInTheDocument()
      expect(screen.getByText('📅')).toBeInTheDocument()
    })
  })

  describe('ISO datetime handling', () => {
    it('should handle ISO datetime strings', () => {
      render(<ExpiryBadge expiryDate="2024-01-20T10:30:00Z" />)
      expect(screen.getByText(/5 days/i)).toBeInTheDocument()
    })

    it('should ignore time component when calculating days', () => {
      render(<ExpiryBadge expiryDate="2024-01-15T23:59:59Z" />)
      expect(screen.getByText(/Today/i)).toBeInTheDocument()
    })
  })

  describe('Visual structure', () => {
    it('should render as a span element', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-20" />)
      expect(container.firstChild?.nodeName).toBe('SPAN')
    })

    it('should have base badge styling classes', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-20" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toContain('inline-flex')
      expect(badge.className).toContain('items-center')
      expect(badge.className).toContain('rounded')
    })

    it('should have proper spacing for touch targets', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-20" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.className).toMatch(/px-\d/)
      expect(badge.className).toMatch(/py-\d/)
    })
  })

  describe('Edge cases', () => {
    it('should handle very far future dates', () => {
      render(<ExpiryBadge expiryDate="2025-01-15" />)
      expect(screen.getByText(/week/i)).toBeInTheDocument()
    })

    it('should handle very old expired dates', () => {
      render(<ExpiryBadge expiryDate="2023-01-15" />)
      expect(screen.getByText(/Expired/i)).toBeInTheDocument()
      expect(screen.getByText('⚠️')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should be readable by screen readers', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-20" />)
      const badge = container.firstChild as HTMLElement
      expect(badge.textContent).toBeTruthy()
    })

    it('should include both icon and text for expired items', () => {
      const { container } = render(<ExpiryBadge expiryDate="2024-01-10" expirySource="scanned" />)
      const badge = container.firstChild as HTMLElement
      // Should contain warning icon, expiry text, and calendar icon
      expect(badge.textContent).toContain('⚠️')
      expect(badge.textContent).toContain('Expired')
      expect(badge.textContent).toContain('📅')
    })
  })
})
