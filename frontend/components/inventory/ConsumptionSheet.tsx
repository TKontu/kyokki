'use client'

/**
 * ConsumptionSheet Component
 * The item sheet behind a tile's "…" (V2, operator ask 2026-09-24: presence, not amounts).
 *
 * The name, "Used up", and the way to the edit sheet - where the date, the place, "Mark as
 * gone" and delete live. It offered every fraction until wave V; a tile tap now uses an item
 * up, and nothing on the iPad counts what is left. The backend still keeps the amounts.
 */

import React from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { useConsumeInventoryItem } from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import type { InventoryItem } from '@/types/inventory'

export interface ConsumptionSheetProps {
  item: InventoryItem | null
  open: boolean
  onClose: () => void
  /** Open the edit sheet for this item instead. */
  onEdit?: () => void
}

export function ConsumptionSheet({ item, open, onClose, onEdit }: ConsumptionSheetProps) {
  const consume = useConsumeInventoryItem()
  const toast = useToast()

  if (!item) return null

  const useUpItem = () => {
    const productName = item.product_name
    consume.mutate(
      { id: item.id, data: { quantity: item.current_quantity } },
      {
        onSuccess: () => toast.success(`Used up · ${productName}`),
        onError: (error) => {
          // 4xx messages come from the API and are meant for people ("Oat Milk has been
          // thrown away"); server and network failures are not.
          const clientError = isAPIError(error) && error.status < 500 && error.message
          toast.error(clientError ? error.message : `Could not update ${productName}`)
        },
      }
    )
    // The fridge already shows the optimistic value, so close right away.
    onClose()
  }

  return (
    <BottomSheet open={open} onClose={onClose} title={item.product_name}>
      <div className="flex flex-col gap-3">
        <Button data-primary size="xl" fullWidth onClick={useUpItem}>
          Used up
        </Button>
        {onEdit && (
          <Button size="lg" variant="ghost" fullWidth onClick={onEdit}>
            Edit item
          </Button>
        )}
      </div>
    </BottomSheet>
  )
}

export default ConsumptionSheet
