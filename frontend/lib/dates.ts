/**
 * Date and Expiry Utilities
 * Handles date calculations and expiry urgency logic for inventory items
 */

export type ExpiryUrgency = 'expired' | 'today' | 'tomorrow' | 'soon' | 'fresh'

/**
 * Local calendar date as YYYY-MM-DD, the value format of <input type="date">.
 * `toISOString` would use UTC and can be a day off in the evening or early morning.
 */
export function toISODate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Today (or `from`) plus `days`, as a local YYYY-MM-DD date. */
export function addDaysISO(days: number, from: Date = new Date()): string {
  const date = new Date(from.getFullYear(), from.getMonth(), from.getDate() + days)
  return toISODate(date)
}

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

/** Days or weeks, in the bare voice the badge uses: no "in", no "ago", no flourish. */
function howLong(days: number): string {
  if (days <= 6) return `${days} day${days === 1 ? '' : 's'}`
  const weeks = Math.floor(days / 7)
  return `${weeks} week${weeks > 1 ? 's' : ''}`
}

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

/**
 * How long ago something happened, for a screen that has to admit when it is out of date.
 *
 * Minutes and hours, in the same bare voice as `howLong`, and then the date: "37 hours ago" is
 * a number nobody converts, and a wall display saying "13 January" is the honest answer. A
 * moment in the future - two clocks disagreeing - reads as "just now" rather than counting up.
 */
export function formatAgo(when: string | number, now: Date = new Date()): string {
  const at = typeof when === 'number' ? when : new Date(when).getTime()
  const ago = now.getTime() - at

  if (ago < MINUTE_MS) return 'just now'
  if (ago < HOUR_MS) {
    const minutes = Math.floor(ago / MINUTE_MS)
    return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  }
  if (ago < DAY_MS) {
    const hours = Math.floor(ago / HOUR_MS)
    return `${hours} hour${hours === 1 ? '' : 's'} ago`
  }
  return new Date(at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long' })
}

/**
 * Format expiry date as human-readable string
 *
 * Every past date used to collapse to the single word "Expired", so yesterday's yoghurt and
 * last June's mince read identically - on a wall display where the expired ones pile up, that
 * is the difference between "use this first" and "this is compost".
 *
 * @param expiryDate - ISO date string
 * @returns Formatted string (e.g., "3 weeks ago", "Yesterday", "Today", "2 days", "1 week")
 */
export function formatExpiryDate(expiryDate: string): string {
  const days = calculateDaysUntilExpiry(expiryDate)

  if (days === -1) return 'Yesterday'
  if (days < 0) return `${howLong(-days)} ago`
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  return howLong(days)
}

/**
 * Get Tailwind CSS color classes based on urgency level
 *
 * @param urgency - ExpiryUrgency level
 * @returns Tailwind CSS classes for background and text
 */
/** Nothing to say about the urgency, so nothing loud: used when `urgency` is not one of the five. */
export const NEUTRAL_EXPIRY_COLOR = 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'

export function getExpiryColor(urgency: ExpiryUrgency): string {
  // Every pair needs a dark variant: these are raw palette colours rather than the
  // ui/ui-dark tokens, so without them the badges stay bright on a dark kitchen screen.
  // Partial, so an urgency arriving from untyped data cannot put `undefined` in a class list.
  const colorMap: Partial<Record<string, string>> = {
    expired: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200',
    today: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200',
    tomorrow: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200',
    soon: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-950 dark:text-yellow-200',
    fresh: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200',
  }

  return colorMap[urgency] ?? NEUTRAL_EXPIRY_COLOR
}
