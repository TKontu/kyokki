'use client'

/**
 * ConsumptionSheet Component
 * Bottom sheet with one-tap consumption: ¼ ½ ¾ Done, or −1 −2 −3 Done for pieces.
 */

import React from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { useConsumeInventoryItem } from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import {
  consumptionOptions,
  formatQuantity,
  isCountable,
  type ConsumptionOption,
} from '@/lib/consumption'
import type { InventoryItem } from '@/types/inventory'

export interface ConsumptionSheetProps {
  item: InventoryItem | null
  open: boolean
  onClose: () => void
}

function successMessage(item: InventoryItem, option: ConsumptionOption): string {
  if (option.key === 'done') {
    return `Used up · ${item.product_name}`
  }
  if (isCountable(item.unit)) {
    return `Consumed ${formatQuantity(option.amount)} ${item.unit} · ${item.product_name}`
  }
  return `Consumed ${option.label} · ${item.product_name}`
}

export function ConsumptionSheet({ item, open, onClose }: ConsumptionSheetProps) {
  const consume = useConsumeInventoryItem()
  const toast = useToast()

  if (!item) return null

  const handleConsume = (option: ConsumptionOption) => {
    // Capture what the toast should say now; the cached item changes optimistically.
    const success = successMessage(item, option)
    const productName = item.product_name

    consume.mutate(
      { id: item.id, data: { quantity: option.amount } },
      {
        onSuccess: () => {
          toast.success(success)
        },
        onError: (error) => {
          // 4xx messages come from the API and are meant for people ("Cannot consume 500 -
          // only 100 available"); server and network failures are not.
          const clientError = isAPIError(error) && error.status < 500 && error.message
          toast.error(clientError ? error.message : `Could not update ${productName}`)
        },
      }
    )
    // The list already shows the optimistic value, so close right away.
    onClose()
  }

  return (
    <BottomSheet open={open} onClose={onClose} title={item.product_name}>
      <p className="mb-4 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
        {`${formatQuantity(item.current_quantity)} / ${formatQuantity(item.initial_quantity)} ${item.unit} left`}
      </p>
      <div className="grid grid-cols-4 gap-3">
        {consumptionOptions(item).map((option) => (
          <Button
            key={option.key}
            size="xl"
            variant={option.key === 'done' ? 'secondary' : 'primary'}
            disabled={option.disabled}
            onClick={() => handleConsume(option)}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </BottomSheet>
  )
}

export default ConsumptionSheet
