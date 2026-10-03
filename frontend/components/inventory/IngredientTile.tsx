'use client'

/**
 * IngredientTile (V1, operator ask 2026-09-24).
 *
 * One item as a small rounded box: its icon and the name, coloured by how soon to eat it, with
 * no numbers. The icon follows one precedence (Q18-G2, lib/productIcon.ts): the product's
 * exact emoji first, then its own generated image when ComfyUI has rendered one, and the
 * category emoji last, including when the image fails to load. The colour's word ("going stale") is in the accessible name, a
 * stale tile has a heavier border and a used-up one a struck-through name, so the colour is
 * never the only signal.
 */

import { useState } from 'react'
import { iconUrl } from '@/lib/api/products'
import { displayName } from '@/lib/displayName'
import { useLanguage } from '@/lib/language'
import { productIconGlyph, resolveProductIcon } from '@/lib/productIcon'
import { STALENESS, stalenessLabel, stalenessOf } from '@/lib/staleness'
import type { InventoryItem } from '@/types/inventory'

export interface IngredientTileProps {
  item: InventoryItem
  /** The tile's own tap. Without it the tile is a picture, not a control. */
  onSelect?: (id: string) => void
  /** "…": everything else about the item. */
  onMore?: (id: string) => void
}

export function IngredientTile({ item, onSelect, onMore }: IngredientTileProps) {
  const [language] = useLanguage()
  const name = displayName(item.product_display_names, item.product_name, language)
  const tier = stalenessOf(item)
  const style = STALENESS[tier]
  const staleWord = stalenessLabel(tier, language)
  const icon = resolveProductIcon({
    emoji: item.product_emoji ?? null,
    iconVersion: item.product_icon_version ?? null,
    categoryIcon: item.category_icon ?? null,
  })
  // The version that failed to load; a newer one gets its own try. Only a generated image
  // can fail this way - an emoji or the category glyph is plain text.
  const [broken, setBroken] = useState<number | null>(null)
  const generatedVersion =
    icon.kind === 'generated' && icon.version !== broken ? icon.version : null
  const face = (
    <>
      {generatedVersion !== null ? (
        // A same-origin <img>: the middleware authenticates the request. next/image is for
        // photos, not a 40 px icon.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={iconUrl(item.product_master_id, generatedVersion)}
          alt=""
          aria-hidden="true"
          width={40}
          height={40}
          className="h-10 w-10"
          onError={() => setBroken(generatedVersion)}
        />
      ) : (
        <span aria-hidden="true" className="text-2xl leading-none">
          {productIconGlyph(icon, item.category_icon)}
        </span>
      )}
      <span
        className={
          'line-clamp-2 break-words text-sm font-medium leading-tight' +
          (tier === 'consumed' ? ' line-through' : '')
        }
      >
        {name}
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
          aria-label={`${name}, ${staleWord}`}
          onClick={() => onSelect(item.id)}
          className={`${box} focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2`}
        >
          {face}
        </button>
      ) : (
        <div aria-label={`${name}, ${staleWord}`} className={box}>
          {face}
        </div>
      )}
      {onMore && (
        <button
          type="button"
          aria-label={`More for ${name}`}
          onClick={() => onMore(item.id)}
          className="absolute right-0 top-0 flex h-touch w-touch items-center justify-center rounded-full text-lg leading-none opacity-70 hover:opacity-100"
        >
          …
        </button>
      )}
    </div>
  )
}

export default IngredientTile
