'use client'

/**
 * FridgeView (V3, operator ask 2026-09-24; drawn as Cielo for the portrait iPad in Q17-B).
 *
 * The stock screen drawn as a fridge. A strip across the top holds what is going stale, as
 * tiles you can tap; below it the fridge (`components/fridge/CieloFridge`) has an area per kind
 * of food, the freezer as a drawer and the pantry in a larder beside it. An area shows its
 * items as coloured dots - one per item, in its staleness colour - rather than a count:
 * nothing on this screen is a number. It fills the height it is given and never scrolls.
 */

import React from 'react'
import { CieloFridge } from '@/components/fridge/CieloFridge'
import { useInventoryList } from '@/hooks/useInventory'
import { buildFridgeView } from '@/lib/fridge'
import type { InventoryItem } from '@/types/inventory'

export interface FridgeViewProps {
  /** A tap on a tile: the item is used up. */
  onConsume?: (id: string) => void
  onMore?: (id: string) => void
  /** Offered on the shelf when something is past its date. */
  onClearExpired?: (items: InventoryItem[]) => void
}

const EMPTY_MESSAGE =
  'No items found. Add one with + Add, or share a receipt to the Telegram bot - you can also ' +
  'scan one on the Scan screen.'

export function FridgeView({ onConsume, onMore, onClearExpired }: FridgeViewProps) {
  const { data: items, isLoading, isError, error } = useInventoryList()

  if (isLoading) {
    return (
      <div className="space-y-3" aria-label="Loading inventory">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-2xl bg-gray-200 dark:bg-gray-700"
            aria-hidden="true"
          />
        ))}
      </div>
    )
  }

  // Only when there is nothing to show instead: the stock already on screen is still the best
  // answer anyone has, and the header's banner says how old it is (H45).
  if (isError && !items) {
    return (
      <p role="alert" className="py-4 text-sm text-red-600 dark:text-red-400">
        {error instanceof Error ? error.message : 'Failed to load inventory.'}
      </p>
    )
  }

  const view = buildFridgeView(items ?? [])
  if (view.areas.every(({ items: inArea }) => inArea.length === 0)) {
    return (
      <p className="py-4 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
        {EMPTY_MESSAGE}
      </p>
    )
  }

  return (
    <CieloFridge
      items={items ?? []}
      onConsume={onConsume}
      onMore={onMore}
      onClearExpired={onClearExpired}
    />
  )
}

export default FridgeView
