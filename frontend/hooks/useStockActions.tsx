'use client'

/**
 * What a tile tap and its "…" do, shared by the fridge (`/`) and an area's grid (`/area/[id]`).
 *
 * A tap uses the item up: no sheet, no success toast (operator, 2026-09-22 and 2026-09-24 -
 * presence, not amounts). The header's Undo names what just happened - the confirmation, and
 * the way back from a mis-tap. In an area's grid the tile stays as a grey one for a day, and a
 * tap on it brings the item back (V4). "…" opens the item's sheet, and from there its edit
 * sheet.
 */

import React, { useState } from 'react'
import { ConsumptionSheet } from '@/components/inventory/ConsumptionSheet'
import { ItemEditSheet } from '@/components/inventory/ItemEditSheet'
import {
  useConsumeInventoryItem,
  useInventoryList,
  useUnconsumeInventoryItem,
} from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import type { InventoryItem, InventoryListParams } from '@/types/inventory'

export function useStockActions(params?: InventoryListParams) {
  // Same query key as the screen's own list, so this shares its cache instead of refetching.
  const list = useInventoryList(params)
  const items = list.data
  const consume = useConsumeInventoryItem()
  const unconsume = useUnconsumeInventoryItem()
  const toast = useToast()
  const [moreId, setMoreId] = useState<string | null>(null)
  // Keep the item being edited even after a delete or "gone" drops it from the list, so the
  // sheet can finish (toast, close) before it unmounts.
  const [editing, setEditing] = useState<InventoryItem | null>(null)

  // Read the live cached item so the sheets reflect optimistic and refetched values.
  const moreItem = items?.find((item) => item.id === moreId) ?? null
  const editingItem = editing ? items?.find((item) => item.id === editing.id) ?? editing : null

  /** `mutateAsync` so every failed tap reports, not only the last of a quick run. */
  const finishItem = (id: string) => {
    const item = items?.find((candidate) => candidate.id === id)
    if (!item) return
    consume
      .mutateAsync({ id, data: { quantity: item.current_quantity } })
      .catch((error) => {
        const clientError = isAPIError(error) && error.status < 500 && error.message
        toast.error(clientError ? error.message : `Could not update ${item.product_name}`)
      })
  }

  /** A used-up (grey) tile comes back; anything else is used up. */
  const toggleItem = (id: string) => {
    const item = items?.find((candidate) => candidate.id === id)
    if (!item) return
    if (item.status !== 'empty') {
      finishItem(id)
      return
    }
    unconsume.mutateAsync(item).catch((error) => {
      const clientError = isAPIError(error) && error.status < 500 && error.message
      toast.error(clientError ? error.message : `Could not bring back ${item.product_name}`)
    })
  }

  const sheets = (
    <>
      <ConsumptionSheet
        item={moreItem}
        open={moreItem !== null}
        onClose={() => setMoreId(null)}
        onEdit={() => {
          setEditing(moreItem)
          setMoreId(null)
        }}
      />
      <ItemEditSheet
        item={editingItem}
        open={editingItem !== null}
        onClose={() => setEditing(null)}
      />
    </>
  )

  return { list, items, finishItem, toggleItem, openMore: setMoreId, sheets }
}
