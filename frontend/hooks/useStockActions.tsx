'use client'

/**
 * What a tile tap and its "…" do, shared by the fridge (`/`) and an area's grid (`/area/[id]`).
 *
 * A tap uses the item up: no sheet, no success toast (operator, 2026-09-22 and 2026-09-24 -
 * presence, not amounts). The tile leaves at once, and the header's Undo names what just
 * happened - the confirmation, and the way back from a mis-tap. "…" opens the item's sheet,
 * and from there its edit sheet.
 */

import React, { useState } from 'react'
import { ConsumptionSheet } from '@/components/inventory/ConsumptionSheet'
import { ItemEditSheet } from '@/components/inventory/ItemEditSheet'
import { useConsumeInventoryItem, useInventoryList } from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import type { InventoryItem } from '@/types/inventory'

export function useStockActions() {
  // Same query key as FridgeView, so this shares its cache instead of refetching.
  const { data: items } = useInventoryList()
  const consume = useConsumeInventoryItem()
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

  return { items, finishItem, openMore: setMoreId, sheets }
}
