/**
 * What the header's Undo says it will reverse (operator, 2026-09-22).
 *
 * Read from across the kitchen, so it names the food and the act - "−1 pcs · Apples",
 * "Thrown away · 3 items" - never the API's vocabulary.
 */

import { formatQuantity } from '@/lib/consumption'
import type { UndoPreview, UndoStep } from '@/types/consumption'

const VERBS: Record<string, string> = {
  use_full: 'Finished',
  discard: 'Thrown away',
  restore: 'Put back',
  correct: 'Correction',
}

function what(step: UndoStep): string {
  if (step.action === 'use_partial') {
    return `−${formatQuantity(step.quantity_consumed)} ${step.unit}`
  }
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
