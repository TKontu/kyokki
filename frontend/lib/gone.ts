/**
 * The Gone screen's rules (operator, 2026-09-22).
 *
 * What left the kitchen, thrown away or finished, newest first. The history keeps everything
 * for good - metrics will be built on it - so the screen, not the data, is what has a window.
 *
 * Every text-producing function here takes an optional `Language` (review F1, round
 * 2026-10-03-1): the planner's original spec never granted this file, so a Finnish screen
 * still read "Today", "7 days" and "You threw away...". No hooks here, by design - the
 * caller (already holding `useLanguage()`/`useT()`) passes the language in. Defaulting to
 * `'en'` keeps every existing caller's output byte-identical without touching their call
 * sites, and keeps the existing positional `now` parameters where tests already pass one.
 */

import type { Language } from '@/lib/language'
import type {
  ActionSummary,
  CategoryWaste,
  ConsumptionAction,
  ConsumptionLogEntry,
  WasteStats,
  WasteWeek,
} from '@/types/consumption'

/** The `Intl` locale for a language choice, same mapping `lib/i18n` uses. */
function localeFor(language: Language): string {
  return language === 'fi' ? 'fi-FI' : 'en-GB'
}

/**
 * Gone means gone: thrown away, or finished. A part-used pack is still in the kitchen, and a
 * correction or a restore is history rather than an event on this screen.
 */
export const GONE_ACTIONS: ConsumptionAction[] = ['discard', 'use_full']

export interface Window {
  label: string
  days: number | null // null looks all the way back
  default?: boolean
}

export const WINDOWS: Window[] = [
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30, default: true },
  { label: 'All', days: null },
]

const WINDOW_LABELS_FI: Record<string, string> = {
  '7 days': '7 päivää',
  '30 days': '30 päivää',
  All: 'Kaikki',
}

/** A window's own label, in the chosen language. `window.label` (English) is the lookup key,
 * not the display text, once a language is given. */
export function windowLabel(window: Window, language: Language = 'en'): string {
  if (language === 'fi') return WINDOW_LABELS_FI[window.label] ?? window.label
  return window.label
}

/** The moment a window starts reading from, or undefined for all of it. */
export function sinceFor(days: number | null, now: Date = new Date()): string | undefined {
  if (days === null) return undefined
  return new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString()
}

export interface DayGroup {
  label: string
  rows: ConsumptionLogEntry[]
}

const DAY_MS = 24 * 60 * 60 * 1000

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

function dayLabel(logged: Date, now: Date, language: Language): string {
  const days = Math.round((startOfDay(now) - startOfDay(logged)) / DAY_MS)
  if (language === 'fi') {
    if (days === 0) return 'Tänään'
    if (days === 1) return 'Eilen'
    return logged.toLocaleDateString(localeFor(language), { day: 'numeric', month: 'long' })
  }
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  return logged.toLocaleDateString(localeFor(language), { day: 'numeric', month: 'long' })
}

/**
 * The rows split into days, in the order they came - the API already sorts them newest first.
 * A day's worth of waste read as one block is the point; a flat list of timestamps is not.
 */
export function groupByDay(
  rows: ConsumptionLogEntry[],
  now: Date = new Date(),
  language: Language = 'en'
): DayGroup[] {
  const groups: DayGroup[] = []
  for (const entry of rows) {
    const label = dayLabel(new Date(entry.logged_at), now, language)
    const last = groups[groups.length - 1]
    if (last?.label === label) last.rows.push(entry)
    else groups.push({ label, rows: [entry] })
  }
  return groups
}

/**
 * "8 items" - how many things, not how much of each (V2, presence not amounts). The history
 * still records the amounts; the screen stopped reading them out.
 */
export function summaryLine(summary: ActionSummary | undefined, language: Language = 'en'): string {
  if (language === 'fi') {
    if (!summary || summary.events === 0) return 'ei mitään'
    return `${summary.events} ${summary.events === 1 ? 'tuote' : 'tuotetta'}`
  }
  if (!summary || summary.events === 0) return 'none'
  return `${summary.events} ${summary.events === 1 ? 'item' : 'items'}`
}

/**
 * "You threw away 3 of 10 things (30 %)" - the Gone screen's headline (planner ruling,
 * 2026-10-02). `null` means too little happened in the window to say anything honest; the
 * screen shows a plain empty state rather than a 0 % or a NaN.
 */
export function wasteRateLine(
  stats: WasteStats | undefined,
  language: Language = 'en'
): string | null {
  if (!stats || stats.total === 0 || stats.rate === null) return null
  const percent = Math.round(stats.rate * 100)
  if (language === 'fi') return `Heitit pois ${stats.discarded}/${stats.total} asiaa (${percent} %)`
  return `You threw away ${stats.discarded} of ${stats.total} things (${percent} %)`
}

/**
 * The categories that waste the most. The service already sorts worst-first and leaves out
 * anything with too few events to mean something; the screen just takes the top few.
 */
export function topWastingCategories(categories: CategoryWaste[], count = 3): CategoryWaste[] {
  return categories.slice(0, count)
}

/** A short label for one week's bar on the trend: "12 Jan" ("12.1." in Finnish - `Intl`'s own
 * short form, which drops the month name rather than abbreviate it oddly). */
export function weekLabel(week: WasteWeek, language: Language = 'en'): string {
  return new Date(`${week.week_start}T00:00:00`).toLocaleDateString(localeFor(language), {
    day: 'numeric',
    month: 'short',
  })
}
