/**
 * How many dots an area's region can show (Q17-B).
 *
 * Everything laid over the drawing - label, emoji, dots - is sized in the drawing's own units
 * and scales with it, so what fits in a region depends on its box alone and can be worked out
 * here rather than measured. When an area holds more than that, the last slot becomes a
 * "more" marker: a region never cuts its dots off without saying so.
 */

import type { Box } from './drawing'

/** A dot's diameter, in drawing units. */
export const DOT = 13
/** The space between two dots. */
export const DOT_GAP = 5
/** From one dot to the next. */
export const DOT_PITCH = DOT + DOT_GAP
/** The region's inner padding, each side. */
export const PAD = 6
/** The label row above the dots, with the gap below it. */
export const HEADER = 30

/** How many dots fit in a region drawn in `box`. */
export function dotCapacity({ w, h }: Box): number {
  const columns = Math.floor((w - PAD * 2 + DOT_GAP) / DOT_PITCH)
  const rows = Math.floor((h - PAD * 2 - HEADER + DOT_GAP) / DOT_PITCH)
  return Math.max(0, columns) * Math.max(0, rows)
}

/** What a region shows of `list`: all of it, or what fits beside a "more" marker. */
export function fitDots<T>(list: T[], capacity: number): { shown: T[]; more: boolean } {
  if (list.length <= capacity) return { shown: list, more: false }
  return { shown: list.slice(0, Math.max(0, capacity - 1)), more: true }
}
