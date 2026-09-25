/**
 * The shelf-life audit (H58, Q15): which numbers to look at first, and which look wrong.
 *
 * A wrong estimate used to be caught in a spreadsheet export. The iPad should show it: a
 * guess before an estimate before a number the cook set, and anything at the edge of - or
 * outside - what the category makes plausible.
 */

import { auditRows, edgeOf } from '../shelfLifeAudit'
import type { Category } from '@/types/category'
import type { ProductMaster } from '@/types/product'

const MEAT: Category = {
  id: 'meat',
  display_name: 'Meat',
  icon: '🥩',
  default_shelf_life_days: 5,
  frozen_shelf_life_days: 180,
  sort_order: 10,
  default_storage: 'refrigerator',
  shelf_life_min_days: 1,
  shelf_life_max_days: 60,
}

const product = (overrides: Partial<ProductMaster> = {}): ProductMaster => ({
  id: 'p1',
  canonical_name: 'Ground beef',
  category: 'meat',
  storage_type: 'refrigerator',
  default_shelf_life_days: 5,
  shelf_life_source: 'category',
  opened_shelf_life_days: null,
  frozen_shelf_life_days: null,
  avg_piece_grams: null,
  pack_grams: null,
  unit_type: 'weight',
  default_unit: 'g',
  default_quantity: null,
  min_stock_quantity: null,
  reorder_quantity: null,
  off_product_id: null,
  off_data: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  ...overrides,
})

describe('edgeOf', () => {
  it('is quiet in the middle of the band', () => {
    expect(edgeOf(30, MEAT)).toBeNull()
  })

  it('flags the shortest end', () => {
    expect(edgeOf(1, MEAT)).toBe('short')
    expect(edgeOf(6, MEAT)).toBe('short') // within a tenth of the band
  })

  it('flags the longest end', () => {
    expect(edgeOf(60, MEAT)).toBe('long')
    expect(edgeOf(55, MEAT)).toBe('long')
  })

  it('flags a number outside the band', () => {
    expect(edgeOf(90, MEAT)).toBe('outside')
    expect(edgeOf(0, MEAT)).toBe('outside')
  })

  it('says nothing without a band to judge by', () => {
    expect(edgeOf(5, undefined)).toBeNull()
  })
})

describe('auditRows', () => {
  it('puts guesses first, then estimates, then what the cook set', () => {
    const rows = auditRows(
      [
        product({ id: 'c', canonical_name: 'Bacon', shelf_life_source: 'cook', default_shelf_life_days: 20 }),
        product({ id: 'm', canonical_name: 'Chicken', shelf_life_source: 'model', default_shelf_life_days: 20 }),
        product({ id: 'g', canonical_name: 'Pork', shelf_life_source: 'category', default_shelf_life_days: 20 }),
      ],
      [MEAT]
    )

    expect(rows.map((r) => r.product.id)).toEqual(['g', 'm', 'c'])
  })

  it('puts flagged rows first within a provenance', () => {
    const rows = auditRows(
      [
        product({ id: 'fine', canonical_name: 'Aaa', shelf_life_source: 'model', default_shelf_life_days: 20 }),
        product({ id: 'edge', canonical_name: 'Zzz', shelf_life_source: 'model', default_shelf_life_days: 58 }),
      ],
      [MEAT]
    )

    expect(rows.map((r) => [r.product.id, r.edge])).toEqual([
      ['edge', 'long'],
      ['fine', null],
    ])
  })

  it('does not flag a placeholder: it is already marked a guess', () => {
    // Perishable placeholders sit near the short end on purpose (H57); flagging every one
    // would drown the estimates the audit is for.
    const [row] = auditRows([product({ default_shelf_life_days: 5 })], [MEAT])

    expect(row.edge).toBeNull()
  })

  it('carries the band it judged by', () => {
    const [row] = auditRows([product()], [MEAT])

    expect(row.band).toEqual([1, 60])
  })
})
