/**
 * ExpiryBadge Component
 * Enhanced expiry badge with date utilities and icon indicators
 */

import React from 'react'
import {
  getExpiryUrgency,
  formatExpiryDate,
  getExpiryColor,
} from '@/lib/dates'

export interface ExpiryBadgeProps {
  /**
   * ISO date string for expiry date
   * e.g., "2024-01-15" or "2024-01-15T10:00:00Z"
   */
  expiryDate: string

  /**
   * Source of the expiry date
   * - scanned: From GS1 DataMatrix barcode (shows 📅 icon)
   * - calculated: Auto-calculated based on category defaults
   * - manual: User-entered date
   */
  expirySource?: 'scanned' | 'calculated' | 'manual'

  /**
   * Additional CSS classes
   */
  className?: string
}

/**
 * ExpiryBadge displays expiry information with color coding and icons
 *
 * Color coding:
 * - Red: Expired (past dates)
 * - Orange: Today or tomorrow
 * - Yellow: 2-3 days away (soon)
 * - Green: 4+ days away (fresh)
 *
 * Icons:
 * - ⚠️: Shown for expired and today items (urgent)
 * - 📅: Shown for scanned dates (accurate from barcode)
 */
export const ExpiryBadge: React.FC<ExpiryBadgeProps> = ({
  expiryDate,
  expirySource,
  className = '',
}) => {
  const urgency = getExpiryUrgency(expiryDate)
  const formattedDate = formatExpiryDate(expiryDate)
  const colorClasses = getExpiryColor(urgency)

  // Show warning icon for expired and today items
  const showWarningIcon = urgency === 'expired' || urgency === 'today'

  // Show calendar icon for scanned dates
  const showCalendarIcon = expirySource === 'scanned'

  // Base badge styles
  const baseStyles = `
    inline-flex items-center justify-center gap-1
    px-2.5 py-1
    text-sm font-medium
    rounded-md
    border transition-colors duration-200
  `

  const combinedClassName = `
    ${baseStyles}
    ${colorClasses}
    ${className}
  `.trim().replace(/\s+/g, ' ')

  return (
    <span className={combinedClassName}>
      {showWarningIcon && <span aria-label="warning">⚠️</span>}
      <span>{formattedDate}</span>
      {showCalendarIcon && <span aria-label="scanned">📅</span>}
    </span>
  )
}

export default ExpiryBadge
