/**
 * What the header's Undo says it will reverse (operator, 2026-09-22).
 *
 * Read from across the kitchen, so it names the food and the act - "Finished · Apples",
 * "Thrown away · 3 items" - never the API's vocabulary, and no amounts (V2, presence not
 * amounts). A partial use can still arrive from outside the iPad; it says "Used some".
 *
 * A correction is named by its sign (Q22). Tapping a grey "used today" tile back sets the
 * item to its full amount, which the API logs as `correct` with a positive amount: to the
 * cook that is "Put back", like a restore. One down (or to the same amount) can only come
 * through the API and reads "Corrected".
 */

import type { UndoPreview, UndoStep } from '@/types/consumption'

const VERBS: Record<string, string> = {
  use_full: 'Finished',
  discard: 'Thrown away',
  restore: 'Put back',
}

function what(step: UndoStep): string {
  if (step.action === 'use_partial') return 'Used some'
  if (step.action === 'correct') return step.quantity_consumed > 0 ? 'Put back' : 'Corrected'
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
