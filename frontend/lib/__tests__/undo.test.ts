/**
 * What the header's Undo says it will reverse. It has to be readable at a glance from across
 * the kitchen, so it names the food and the act, not the API's vocabulary.
 */

import { describeUndo } from '../undo'
import type { UndoPreview, UndoStep } from '@/types/consumption'

const step = (overrides: Partial<UndoStep> = {}): UndoStep => ({
  inventory_item_id: 'i1',
  product_name: 'Apples',
  unit: 'pcs',
  action: 'use_partial',
  quantity_consumed: 1,
  ...overrides,
})

const preview = (...steps: UndoStep[]): UndoPreview => ({
  batch_id: 'b1',
  logged_at: '2026-09-22T08:00:00+00:00',
  steps,
})

describe('describeUndo', () => {
  it.each([
    // Presence, not amounts (V2): a partial use says so, not how much
    [step(), 'Used some · Apples'],
    [step({ unit: 'dl', quantity_consumed: 2.5, product_name: 'Milk' }), 'Used some · Milk'],
    [step({ action: 'use_full' }), 'Finished · Apples'],
    [step({ action: 'discard' }), 'Thrown away · Apples'],
    [step({ action: 'restore' }), 'Put back · Apples'],
    [step({ action: 'correct' }), 'Correction · Apples'],
  ])('names one change by what happened to the food', (only, text) => {
    expect(describeUndo(preview(only))).toBe(text)
  })

  it('counts a cleared shelf rather than listing it', () => {
    const shelf = preview(
      step({ action: 'discard' }),
      step({ action: 'discard', product_name: 'Milk' }),
      step({ action: 'discard', product_name: 'Cream' })
    )

    expect(describeUndo(shelf)).toBe('Thrown away · 3 items')
  })

  it('shows an action this build has never heard of rather than hiding it', () => {
    expect(describeUndo(preview(step({ action: 'composted' })))).toBe('composted · Apples')
  })
})
