/**
 * The Gone screen's rules (operator, 2026-09-22).
 *
 * What left the kitchen, thrown away or finished, newest first. The history keeps everything
 * for good - metrics will be built on it - so the screen, not the data, is what has a window.
 */

import type { ActionSummary, ConsumptionAction, ConsumptionLogEntry } from '@/types/consumption'

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

function dayLabel(logged: Date, now: Date): string {
  const days = Math.round((startOfDay(now) - startOfDay(logged)) / DAY_MS)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  return logged.toLocaleDateString('en-GB', { day: 'numeric', month: 'long' })
}

/**
 * The rows split into days, in the order they came - the API already sorts them newest first.
 * A day's worth of waste read as one block is the point; a flat list of timestamps is not.
 */
export function groupByDay(
  rows: ConsumptionLogEntry[],
  now: Date = new Date()
): DayGroup[] {
  const groups: DayGroup[] = []
  for (const entry of rows) {
    const label = dayLabel(new Date(entry.logged_at), now)
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
export function summaryLine(summary: ActionSummary | undefined): string {
  if (!summary || summary.events === 0) return 'none'
  return `${summary.events} ${summary.events === 1 ? 'item' : 'items'}`
}
