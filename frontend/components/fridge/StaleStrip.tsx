'use client'

/**
 * The going-stale strip across the top of the fridge (Q17-B, portrait iPad).
 *
 * What is going stale, stalest first, as tiles to tap: a tap uses the item up, "…" opens its
 * sheet. The strip is one row that never scrolls sideways: when there are more tiles than
 * fit, the last place goes to a "More" tile that opens every going-stale item in a sheet. No
 * numbers - the tile says "More", not how many.
 *
 * The tiles are `IngredientTile`s, fitted to the strip from outside (review of #113): a long
 * one-word Finnish name breaks and hyphenates inside its cell instead of spilling over its
 * neighbours, and the tile's "…" gets a full touch-size target in the corner.
 */

import React, { useEffect, useState } from 'react'
import { IngredientTile } from '@/components/inventory/IngredientTile'
import BottomSheet from '@/components/ui/BottomSheet'
import type { InventoryItem } from '@/types/inventory'

/** Tiles in the strip's one row, the "More" tile included: about 120 px each at 810 px wide. */
export const STALE_STRIP_MAX = 6

/**
 * A tile's cell. It clips; the name inside may break anywhere and hyphenates as Finnish (the
 * `lang` goes on the cell), so its min-content width no longer pushes past the cell. The
 * tile's own "…" is 32 px, under the touch minimum: here it becomes a 44 px corner target.
 */
const CELL =
  'min-w-0 overflow-hidden rounded-2xl ' +
  '[&_span]:max-w-full [&_span]:hyphens-auto [&_span]:[overflow-wrap:anywhere] ' +
  "[&_[aria-label^='More_for']]:right-0 [&_[aria-label^='More_for']]:top-0 " +
  "[&_[aria-label^='More_for']]:h-touch [&_[aria-label^='More_for']]:w-touch"

export interface StaleStripProps {
  /** Going stale, stalest first. */
  items: InventoryItem[]
  /** Past their date: what "Clear expired" offers to throw away. */
  expired: InventoryItem[]
  onConsume?: (id: string) => void
  onMore?: (id: string) => void
  onClearExpired?: (items: InventoryItem[]) => void
}

export function StaleStrip({ items, expired, onConsume, onMore, onClearExpired }: StaleStripProps) {
  const [showAll, setShowAll] = useState(false)
  // Everything in the list used up: close it, or the next item going stale would open it
  const empty = items.length === 0
  useEffect(() => {
    if (empty) setShowAll(false)
  }, [empty])
  if (empty) return null

  const overflow = items.length > STALE_STRIP_MAX
  const shown = overflow ? items.slice(0, STALE_STRIP_MAX - 1) : items
  // One sheet at a time: the list closes before the item's own sheet opens over it
  const moreFromList = onMore
    ? (id: string) => {
        setShowAll(false)
        onMore(id)
      }
    : undefined

  return (
    <section
      aria-label="Going stale"
      className="flex shrink-0 flex-col gap-1 rounded-3xl border-2 border-sky-200 bg-sky-50 px-3 pb-3 pt-1 dark:border-sky-900 dark:bg-slate-900"
    >
      <h2 className="flex min-h-touch items-center gap-2 text-base font-semibold text-rose-700 dark:text-rose-300">
        Going stale
        {onClearExpired && expired.length > 0 && (
          <button
            type="button"
            onClick={() => onClearExpired(expired)}
            className="ml-auto min-h-touch px-1 text-sm font-medium underline"
          >
            Clear expired
          </button>
        )}
      </h2>
      <ul className="grid grid-cols-6 gap-2">
        {shown.map((item) => (
          <li key={item.id} lang="fi" className={CELL}>
            <IngredientTile item={item} onSelect={onConsume} onMore={onMore} />
          </li>
        ))}
        {overflow && (
          <li className="min-w-0">
            <button
              type="button"
              aria-label="All going stale"
              onClick={() => setShowAll(true)}
              className={
                'flex h-full min-h-touch-lg w-full flex-col items-center justify-center gap-1 ' +
                'rounded-2xl border-2 border-dashed border-rose-300 bg-white/70 px-2 py-3 ' +
                'text-sm font-semibold text-rose-800 hover:bg-white focus:outline-none ' +
                'focus-visible:ring-2 focus-visible:ring-offset-2 dark:border-rose-400/60 ' +
                'dark:bg-slate-800/70 dark:text-rose-200 dark:hover:bg-slate-800'
              }
            >
              <span aria-hidden="true" className="text-2xl leading-none">
                ⋯
              </span>
              More
            </button>
          </li>
        )}
      </ul>
      <BottomSheet open={showAll} onClose={() => setShowAll(false)} title="Going stale">
        <ul className="grid grid-cols-4 gap-2 sm:grid-cols-5">
          {items.map((item) => (
            <li key={item.id} lang="fi" className={CELL}>
              <IngredientTile item={item} onSelect={onConsume} onMore={moreFromList} />
            </li>
          ))}
        </ul>
      </BottomSheet>
    </section>
  )
}

export default StaleStrip
