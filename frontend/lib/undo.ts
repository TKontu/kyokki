/**
 * What the header's Undo says it will reverse (operator, 2026-09-22).
 *
 * Read from across the kitchen, so it names the food and the act - "Finished · Apples",
 * "Thrown away · 3 items" - never the API's vocabulary, and no amounts (V2, presence not
 * amounts). A partial use can still arrive from outside the iPad; it says "Used some".
 *
 * A correction reads "Put back" (Q22) when it went up - the only one the iPad itself makes
 * is tapping a grey "used today" tile back, which sets the item to its full amount - and
 * "Corrected down" when the log says it went the other way. `direction` is null for a
 * correction logged before the backend could tell (an old row, or one this build predates);
 * that reads "Put back" too, same as before this build knew to ask (2026-10-02).
 *
 * `describeUndo` takes an optional `Language` (review F1, round 2026-10-03-1): the planner's
 * original spec never granted this file, so a Finnish screen still read "Used some · Apples".
 * No hooks here, by design - the caller (already holding `useLanguage()`) passes the language
 * in. Defaulting to `'en'` keeps every existing caller's output byte-identical. `product_name`
 * (the API's own text, not `display_names`) is unaffected either way - `UndoStep` carries no
 * display-name map to resolve it from.
 */

import type { UndoPreview, UndoStep } from '@/types/consumption'
import type { Language } from './language'

const VERBS: Record<string, string> = {
  use_full: 'Finished',
  discard: 'Thrown away',
  restore: 'Put back',
  correct: 'Put back',
}

const VERBS_FI: Record<string, string> = {
  use_full: 'Käytetty loppuun',
  discard: 'Heitetty pois',
  restore: 'Palautettu',
  correct: 'Palautettu',
}

function what(step: UndoStep, language: Language): string {
  if (language === 'fi') {
    if (step.action === 'use_partial') return 'Käytetty osittain'
    if (step.action === 'correct' && step.direction === 'down') return 'Korjattu alaspäin'
    // An action this build does not know still says something true: its own name (H04)
    return VERBS_FI[step.action] ?? step.action
  }
  if (step.action === 'use_partial') return 'Used some'
  if (step.action === 'correct' && step.direction === 'down') return 'Corrected down'
  return VERBS[step.action] ?? step.action
}

export function describeUndo(preview: UndoPreview, language: Language = 'en'): string {
  const [first] = preview.steps
  if (preview.steps.length === 1) {
    return `${what(first, language)} · ${first.product_name}`
  }
  // Several rows are one action - a cleared shelf, or a shelf put back. Finnish numeral
  // agreement: a count other than one takes the partitive singular ("3 tuotetta"), never the
  // bare partitive plural a number-less count would use.
  if (language === 'fi') return `${what(first, language)} · ${preview.steps.length} tuotetta`
  return `${what(first, language)} · ${preview.steps.length} items`
}
