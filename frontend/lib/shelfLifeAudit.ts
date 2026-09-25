/**
 * The shelf-life audit (H58, Q15).
 *
 * Which products' shelf lives to look at first, and which look wrong. Provenance orders the
 * list - a category guess, then a model estimate, then a number the cook set - and a number
 * at the edge of its category's plausible band (or outside it) is flagged, because that is
 * where a confident wrong estimate shows. The band is the one the catalog estimate already
 * enforces on the backend, sent with each category.
 */

import type { Category } from '@/types/category'
import type { ProductMaster, ShelfLifeSource } from '@/types/product'

export type Edge = 'short' | 'long' | 'outside'

export interface AuditRow {
  product: ProductMaster
  edge: Edge | null
  band: [number, number] | null
}

const PROVENANCE_ORDER: Record<ShelfLifeSource, number> = {
  category: 0,
  model: 1,
  cook: 2,
}

/** Within this share of the band's width from either end counts as "at the edge". */
const EDGE_SHARE = 0.1

export function edgeOf(days: number, category: Category | undefined): Edge | null {
  if (!category) return null
  const low = category.shelf_life_min_days
  const high = category.shelf_life_max_days
  if (days < low || days > high) return 'outside'
  const margin = Math.max(1, Math.round((high - low) * EDGE_SHARE))
  if (days <= low + margin) return 'short'
  if (days >= high - margin) return 'long'
  return null
}

export function auditRows(products: ProductMaster[], categories: Category[]): AuditRow[] {
  const byId = new Map(categories.map((c) => [c.id, c]))
  return products
    .map((product) => {
      const category = byId.get(product.category)
      return {
        product,
        // A placeholder is already marked a guess, and perishable ones sit near the short
        // end on purpose (H57); flagging them would drown the estimates.
        edge:
          product.shelf_life_source === 'category'
            ? null
            : edgeOf(product.default_shelf_life_days, category),
        band: category
          ? ([category.shelf_life_min_days, category.shelf_life_max_days] as [number, number])
          : null,
      }
    })
    .sort(
      (a, b) =>
        (PROVENANCE_ORDER[a.product.shelf_life_source] ?? 0) -
          (PROVENANCE_ORDER[b.product.shelf_life_source] ?? 0) ||
        Number(b.edge !== null) - Number(a.edge !== null) ||
        a.product.canonical_name.localeCompare(b.product.canonical_name)
    )
}
