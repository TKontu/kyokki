/**
 * Consumption history types (H46)
 * Mirror backend schema: /backend/app/schemas/consumption_log.py
 */

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
  inventory_item_id: string
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
