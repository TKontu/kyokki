/**
 * What the header's Undo says it will reverse (operator, 2026-09-22).
 *
 * Read from across the kitchen, so it names the food and the act - "Finished · Apples",
 * "Thrown away · 3 items" - never the API's vocabulary, and no amounts (V2, presence not
 * amounts). A partial use can still arrive from outside the iPad; it says "Used some".
 *
 * A correction reads "Put back" (Q22). The only one the iPad makes is tapping a grey "used
 * today" tile back, which sets the item to its full amount and is logged as `correct`. The
 * undo preview cannot say which way a correction went - the log stores its amount unsigned
 * (`crud/consumption_log.py`) and sends no direction - so one made downwards through the API
 * reads "Put back" too. Naming the direction waits on the backend (a recorded follow-up).
 */

import type { UndoPreview, UndoStep } from '@/types/consumption'

const VERBS: Record<string, string> = {
  use_full: 'Finished',
  discard: 'Thrown away',
  restore: 'Put back',
  correct: 'Put back',
}

function what(step: UndoStep): string {
  if (step.action === 'use_partial') return 'Used some'
  // An action this build does not know still says something true: its own name (H04)
  return VERBS[step.action] ?? step.action
}

export function describeUndo(preview: UndoPreview): string {
  const [first] = preview.steps
  if (preview.steps.length === 1) {
    return `${what(first)} · ${first.product_name}`
  }
  // Several rows are one action - a cleared shelf, or a shelf put back
  return `${what(first)} · ${preview.steps.length} items`
}
