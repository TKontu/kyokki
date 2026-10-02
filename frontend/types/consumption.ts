/**
 * Consumption history types (H46)
 * Mirror backend schema: /backend/app/schemas/consumption_log.py
 */

import type { InventoryItemStatus } from './inventory'
import type { Vocabulary } from './vocabulary'

/**
 * What happened to an item's quantity. `discard` is waste; the two `use_` values are food that
 * was eaten; `restore` and `correct` are neither, and a waste total must not count them.
 */
export type ConsumptionAction =
  | 'use_partial'
  | 'use_full'
  | 'discard'
  | 'restore'
  | 'correct'

/** One event in an item's history, readable on its own. */
export interface ConsumptionLogEntry {
  id: string
  inventory_item_id: string | null // null once the item was deleted; the record stays
  item_status: Vocabulary<InventoryItemStatus> | null // null when the item is gone
  product_master_id: string
  product_name: string
  unit: string // The unit both quantities are in
  action: Vocabulary<ConsumptionAction>
  quantity_consumed: number // How much the event moved, always positive
  quantity_after: number // What was left after it
  logged_at: string // ISO datetime
}

export interface ConsumptionLogParams {
  action?: ConsumptionAction[] // Only these kinds of event
  product_master_id?: string
  inventory_item_id?: string
  since?: string // ISO datetime, inclusive
  until?: string // ISO datetime, exclusive
  limit?: number // 1-200, default 50
  offset?: number
}

/** One change the header's Undo would reverse. */
export interface UndoStep {
  inventory_item_id: string
  product_name: string
  unit: string
  action: Vocabulary<ConsumptionAction>
  quantity_consumed: number
}

/** The most recent action on stock, as one step for Undo: one item, or a whole cleared shelf. */
export interface UndoPreview {
  batch_id: string // Send back to undo exactly this, and nothing newer
  logged_at: string // ISO datetime
  steps: UndoStep[]
}

export interface UndoResponse {
  undone: number // How many items were put back
}

/** What one kind of event added up to in a window. Grams and pieces are kept apart. */
export interface ActionSummary {
  events: number
  totals: Record<string, number>
}

/** `GET /api/consumption-log/summary`: action -> its counts. Absent means nothing happened. */
export type ConsumptionSummary = Partial<Record<ConsumptionAction, ActionSummary>> &
  Record<string, ActionSummary | undefined>

/** How one category's events split between thrown away and finished (planner ruling, 2026-10-02). */
export interface CategoryWaste {
  category: string
  display_name: string
  discarded: number
  finished: number
  total: number
  rate: number // discarded / total
}

/**
 * `GET /api/consumption-log/waste`: the Gone screen's headline for a window, plus where it is
 * worst. Counted by events, not amounts - grams and pieces do not add up. A discard a later
 * restore undid is not waste; corrections, part-uses and restores never enter this count.
 */
export interface WasteStats {
  discarded: number
  finished: number
  total: number
  rate: number | null // null with nothing in the window - never render this as 0%
  categories: CategoryWaste[] // categories with at least 3 events, worst waste rate first
}

/** One ISO week of the trend, Europe/Helsinki (the app's timezone), Monday start. */
export interface WasteWeek {
  week_start: string // ISO date, the week's Monday
  discarded: number
  finished: number
  total: number
  rate: number | null
}

/** `GET /api/consumption-log/waste/trend`: the last 8 ISO weeks, oldest first. */
export interface WasteTrend {
  weeks: WasteWeek[]
}
