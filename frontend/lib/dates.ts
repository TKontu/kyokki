/**
 * Date and Expiry Utilities
 * Handles date calculations and expiry urgency logic for inventory items
 */

export type ExpiryUrgency = 'expired' | 'today' | 'tomorrow' | 'soon' | 'fresh'

/**
 * Calculate days until expiry from a given date
 * Positive = future, Negative = past, 0 = today
 *
 * @param expiryDate - ISO date string (e.g., "2024-01-15" or "2024-01-15T10:00:00Z")
 * @returns Number of days until expiry (can be negative)
 */
export function calculateDaysUntilExpiry(expiryDate: string): number {
  // Extract just the date part to avoid timezone issues
  const dateOnly = expiryDate.split('T')[0]

  const today = new Date()
  today.setHours(0, 0, 0, 0) // Reset time to start of day

  const expiry = new Date(dateOnly)
  expiry.setHours(0, 0, 0, 0) // Reset time to start of day

  const diffTime = expiry.getTime() - today.getTime()
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24))

  return diffDays
}

/**
 * Get urgency level based on expiry date
 *
 * @param expiryDate - ISO date string
 * @returns ExpiryUrgency level
 */
export function getExpiryUrgency(expiryDate: string): ExpiryUrgency {
  const days = calculateDaysUntilExpiry(expiryDate)

  if (days < 0) return 'expired'
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days <= 3) return 'soon'
  return 'fresh'
}

/**
 * Format expiry date as human-readable string
 *
 * @param expiryDate - ISO date string
 * @returns Formatted string (e.g., "Expired", "Today", "2 days", "1 week")
 */
export function formatExpiryDate(expiryDate: string): string {
  const days = calculateDaysUntilExpiry(expiryDate)

  if (days < 0) return 'Expired'
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days <= 6) return `${days} days`

  // For 7+ days, show weeks
  const weeks = Math.floor(days / 7)
  return `${weeks} week${weeks > 1 ? 's' : ''}`
}

/**
 * Get Tailwind CSS color classes based on urgency level
 *
 * @param urgency - ExpiryUrgency level
 * @returns Tailwind CSS classes for background and text
 */
export function getExpiryColor(urgency: ExpiryUrgency): string {
  const colorMap: Record<ExpiryUrgency, string> = {
    expired: 'bg-red-100 text-red-800',
    today: 'bg-orange-100 text-orange-800',
    tomorrow: 'bg-orange-100 text-orange-800',
    soon: 'bg-yellow-100 text-yellow-800',
    fresh: 'bg-green-100 text-green-800',
  }

  return colorMap[urgency]
}
