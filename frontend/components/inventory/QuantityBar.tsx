/**
 * QuantityBar Component
 * Progress bar showing current/initial quantity ratio with color coding
 */

import React from 'react'

export interface QuantityBarProps {
  /**
   * Current quantity remaining
   */
  current: number

  /**
   * Initial/original quantity
   */
  initial: number

  /**
   * Unit of measurement (e.g., "ml", "g", "L", "pcs")
   */
  unit: string

  /**
   * Compact mode - smaller bar, no text label
   */
  compact?: boolean

  /**
   * Additional CSS classes
   */
  className?: string
}

/**
 * Get color class based on percentage remaining
 * - Green: 75-100%
 * - Yellow: 50-74%
 * - Orange: 25-49%
 * - Red: 0-24%
 */
function getQuantityColor(percentage: number): string {
  if (percentage >= 75) return 'bg-green-500'
  if (percentage >= 50) return 'bg-yellow-500'
  if (percentage >= 25) return 'bg-orange-500'
  return 'bg-red-500'
}

/**
 * Format quantity for display
 * - Whole numbers: no decimals
 * - Decimals: up to 2 decimal places, trimmed
 */
function formatQuantity(value: number): string {
  if (Number.isInteger(value)) {
    return value.toString()
  }
  // Round to 2 decimal places and remove trailing zeros
  return parseFloat(value.toFixed(2)).toString()
}

/**
 * QuantityBar displays remaining quantity as a progress bar
 *
 * Color coding:
 * - Green: 75-100% remaining (plenty left)
 * - Yellow: 50-74% remaining (half used)
 * - Orange: 25-49% remaining (running low)
 * - Red: <25% remaining (almost empty)
 */
export const QuantityBar: React.FC<QuantityBarProps> = ({
  current,
  initial,
  unit,
  compact = false,
  className = '',
}) => {
  // Calculate percentage (handle edge cases)
  const percentage = initial > 0 ? Math.min(100, (current / initial) * 100) : 0
  const roundedPercentage = Math.round(percentage)

  // Format percentage for width style
  const widthPercentage = percentage.toFixed(1)

  // Get color based on percentage
  const colorClass = getQuantityColor(percentage)

  // Format quantities for display
  const formattedCurrent = formatQuantity(current)
  const formattedInitial = formatQuantity(initial)

  // Aria label for accessibility
  const ariaLabel = `${formattedCurrent} of ${formattedInitial} ${unit} remaining`

  // Base container styles
  const containerClasses = `flex flex-col gap-1 ${className}`.trim()

  // Track styles (background)
  const trackClasses = compact
    ? 'h-1 w-full bg-ui-bg-tertiary dark:bg-ui-dark-bg-tertiary rounded-full overflow-hidden'
    : 'h-2 w-full bg-ui-bg-tertiary dark:bg-ui-dark-bg-tertiary rounded-full overflow-hidden'

  // Progress bar styles
  const progressClasses = `h-full transition-all duration-300 rounded-full ${colorClass}`

  return (
    <div className={containerClasses}>
      {/* Text label (hidden in compact mode) */}
      {!compact && (
        <div className="flex justify-between items-center text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          <span>
            {formattedCurrent} / {formattedInitial} {unit}
          </span>
          <span className="text-xs text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
            {roundedPercentage}%
          </span>
        </div>
      )}

      {/* Progress bar */}
      <div
        data-testid="quantity-track"
        className={trackClasses}
        role="progressbar"
        aria-valuenow={roundedPercentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ariaLabel}
      >
        <div
          data-testid="quantity-progress"
          className={progressClasses}
          style={{ width: `${widthPercentage}%` }}
        />
      </div>
    </div>
  )
}

export default QuantityBar
