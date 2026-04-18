/**
 * QuantityBar Component Tests (TDD)
 * Progress bar showing current/initial quantity ratio with color coding
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { QuantityBar } from '../QuantityBar'

describe('QuantityBar', () => {
  describe('Basic rendering', () => {
    it('should render with current and initial quantity', () => {
      render(<QuantityBar current={750} initial={1000} unit="ml" />)
      expect(screen.getByText(/750/)).toBeInTheDocument()
      expect(screen.getByText(/1000/)).toBeInTheDocument()
    })

    it('should display unit label', () => {
      render(<QuantityBar current={750} initial={1000} unit="ml" />)
      expect(screen.getByText(/ml/)).toBeInTheDocument()
    })

    it('should render with custom className', () => {
      const { container } = render(
        <QuantityBar current={500} initial={1000} unit="g" className="custom-class" />
      )
      expect(container.firstChild).toHaveClass('custom-class')
    })
  })

  describe('Quantity display formatting', () => {
    it('should format whole numbers without decimals', () => {
      render(<QuantityBar current={500} initial={1000} unit="ml" />)
      expect(screen.getByText(/500/)).toBeInTheDocument()
    })

    it('should format decimal quantities with one decimal place', () => {
      render(<QuantityBar current={1.5} initial={2} unit="L" />)
      expect(screen.getByText(/1\.5/)).toBeInTheDocument()
    })

    it('should handle zero current quantity', () => {
      render(<QuantityBar current={0} initial={1000} unit="ml" />)
      expect(screen.getByText(/0 \/ 1000/)).toBeInTheDocument()
    })

    it('should handle small quantities', () => {
      render(<QuantityBar current={0.25} initial={1} unit="kg" />)
      expect(screen.getByText(/0\.25/)).toBeInTheDocument()
    })
  })

  describe('Progress bar percentage', () => {
    it('should show 100% width when full', () => {
      const { container } = render(
        <QuantityBar current={1000} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar).toHaveStyle({ width: '100%' })
    })

    it('should show 75% width for 75% remaining', () => {
      const { container } = render(
        <QuantityBar current={750} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar).toHaveStyle({ width: '75%' })
    })

    it('should show 50% width for half remaining', () => {
      const { container } = render(
        <QuantityBar current={500} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar).toHaveStyle({ width: '50%' })
    })

    it('should show 0% width when empty', () => {
      const { container } = render(
        <QuantityBar current={0} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar).toHaveStyle({ width: '0%' })
    })

    it('should cap at 100% even if current exceeds initial', () => {
      const { container } = render(
        <QuantityBar current={1200} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar).toHaveStyle({ width: '100%' })
    })
  })

  describe('Color coding based on percentage', () => {
    it('should apply green color for 75-100% remaining', () => {
      const { container } = render(
        <QuantityBar current={800} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar?.className).toContain('bg-green')
    })

    it('should apply yellow color for 50-74% remaining', () => {
      const { container } = render(
        <QuantityBar current={600} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar?.className).toContain('bg-yellow')
    })

    it('should apply orange color for 25-49% remaining', () => {
      const { container } = render(
        <QuantityBar current={300} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar?.className).toContain('bg-orange')
    })

    it('should apply red color for <25% remaining', () => {
      const { container } = render(
        <QuantityBar current={100} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar?.className).toContain('bg-red')
    })

    it('should apply red color for empty', () => {
      const { container } = render(
        <QuantityBar current={0} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar?.className).toContain('bg-red')
    })
  })

  describe('Visual structure', () => {
    it('should render as a div element', () => {
      const { container } = render(
        <QuantityBar current={500} initial={1000} unit="ml" />
      )
      expect(container.firstChild?.nodeName).toBe('DIV')
    })

    it('should have progress bar background track', () => {
      const { container } = render(
        <QuantityBar current={500} initial={1000} unit="ml" />
      )
      const track = container.querySelector('[data-testid="quantity-track"]')
      expect(track).toBeInTheDocument()
      expect(track?.className).toContain('bg-')
    })

    it('should have proper sizing classes', () => {
      const { container } = render(
        <QuantityBar current={500} initial={1000} unit="ml" />
      )
      const track = container.querySelector('[data-testid="quantity-track"]')
      expect(track?.className).toContain('h-')
      expect(track?.className).toContain('rounded')
    })
  })

  describe('Compact mode', () => {
    it('should render smaller when compact is true', () => {
      const { container } = render(
        <QuantityBar current={500} initial={1000} unit="ml" compact />
      )
      const track = container.querySelector('[data-testid="quantity-track"]')
      expect(track?.className).toContain('h-1')
    })

    it('should hide text label in compact mode', () => {
      render(<QuantityBar current={500} initial={1000} unit="ml" compact />)
      expect(screen.queryByText(/500/)).not.toBeInTheDocument()
    })
  })

  describe('Different units', () => {
    it('should display ml units', () => {
      render(<QuantityBar current={500} initial={1000} unit="ml" />)
      expect(screen.getByText(/ml/)).toBeInTheDocument()
    })

    it('should display L units', () => {
      render(<QuantityBar current={1} initial={2} unit="L" />)
      expect(screen.getByText(/L/)).toBeInTheDocument()
    })

    it('should display g units', () => {
      render(<QuantityBar current={250} initial={500} unit="g" />)
      expect(screen.getByText(/g/)).toBeInTheDocument()
    })

    it('should display pcs units', () => {
      render(<QuantityBar current={3} initial={6} unit="pcs" />)
      expect(screen.getByText(/pcs/)).toBeInTheDocument()
    })
  })

  describe('Edge cases', () => {
    it('should handle very small percentages', () => {
      const { container } = render(
        <QuantityBar current={1} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      // Should still show some width, even if tiny
      expect(progressBar).toHaveStyle({ width: '0.1%' })
    })

    it('should handle large quantities', () => {
      render(<QuantityBar current={5000} initial={10000} unit="ml" />)
      expect(screen.getByText(/5000/)).toBeInTheDocument()
      expect(screen.getByText(/10000/)).toBeInTheDocument()
    })

    it('should handle initial quantity of zero gracefully', () => {
      const { container } = render(
        <QuantityBar current={0} initial={0} unit="ml" />
      )
      const progressBar = container.querySelector('[data-testid="quantity-progress"]')
      expect(progressBar).toHaveStyle({ width: '0%' })
    })
  })

  describe('Accessibility', () => {
    it('should have proper aria attributes', () => {
      const { container } = render(
        <QuantityBar current={750} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[role="progressbar"]')
      expect(progressBar).toBeInTheDocument()
      expect(progressBar).toHaveAttribute('aria-valuenow', '75')
      expect(progressBar).toHaveAttribute('aria-valuemin', '0')
      expect(progressBar).toHaveAttribute('aria-valuemax', '100')
    })

    it('should have descriptive aria-label', () => {
      const { container } = render(
        <QuantityBar current={750} initial={1000} unit="ml" />
      )
      const progressBar = container.querySelector('[role="progressbar"]')
      expect(progressBar).toHaveAttribute('aria-label', '750 of 1000 ml remaining')
    })
  })
})
