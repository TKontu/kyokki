'use client'

/**
 * IngredientTile (V1, operator ask 2026-09-24).
 *
 * One item as a small rounded box: the category emoji and the name, coloured by how soon to
 * eat it, with no numbers. The colour's word ("going stale") is in the accessible name, a
 * stale tile has a heavier border and a used-up one a struck-through name, so the colour is
 * never the only signal.
 */

import { STALENESS, stalenessOf } from '@/lib/staleness'
import type { InventoryItem } from '@/types/inventory'

export interface IngredientTileProps {
  item: InventoryItem
  /** The tile's own tap. Without it the tile is a picture, not a control. */
  onSelect?: (id: string) => void
  /** "…": everything else about the item. */
  onMore?: (id: string) => void
}

export function IngredientTile({ item, onSelect, onMore }: IngredientTileProps) {
  const tier = stalenessOf(item)
  const style = STALENESS[tier]
  const face = (
    <>
      <span aria-hidden="true" className="text-2xl leading-none">
        {item.category_icon ?? ''}
      </span>
      <span
        className={
          'line-clamp-2 break-words text-sm font-medium leading-tight' +
          (tier === 'consumed' ? ' line-through' : '')
        }
      >
        {item.product_name}
      </span>
    </>
  )
  const box =
    'flex h-full min-h-touch-lg w-full flex-col items-center justify-center gap-1 rounded-2xl ' +
    `px-2 py-3 text-center ${tier === 'stale' ? 'border-4' : 'border-2'} ${style.tile}`

  return (
    <div className="relative h-full">
      {onSelect ? (
        <button
          type="button"
          aria-label={`${item.product_name}, ${style.label}`}
          onClick={() => onSelect(item.id)}
          className={`${box} focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2`}
        >
          {face}
        </button>
      ) : (
        <div aria-label={`${item.product_name}, ${style.label}`} className={box}>
          {face}
        </div>
      )}
      {onMore && (
        <button
          type="button"
          aria-label={`More for ${item.product_name}`}
          onClick={() => onMore(item.id)}
          className="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded-full text-lg leading-none opacity-70 hover:opacity-100"
        >
          …
        </button>
      )}
    </div>
  )
}

export default IngredientTile
