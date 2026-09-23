'use client'

/**
 * ConsumptionSheet Component
 * Every amount the item offers, behind the card's "…". The card's own buttons cover the usual
 * step and finishing it in one tap (operator, 2026-09-22); this is for the rest. The options
 * come from the item itself (Q4): pieces lead with a large "1", measured things offer fractions
 * labelled with the amount. Edit lives here too, which is what took it off the card.
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
  /** Open the edit sheet for this item instead. */
  onEdit?: () => void
}

function successMessage(item: InventoryItem, option: ConsumptionOption): string {
  if (option.key === 'done') {
    return `Used up · ${item.product_name}`
  }
  if (isCountable(item.unit)) {
    return `Consumed ${formatQuantity(option.amount)} ${item.unit} · ${item.product_name}`
  }
  return `Consumed ${formatQuantity(option.amount)} ${item.unit} · ${item.product_name}`
}

export function ConsumptionSheet({ item, open, onClose, onEdit }: ConsumptionSheetProps) {
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
      {(() => {
        const options = consumptionOptions(item)
        const lead = options.find((option) => option.primary)
        const rest = options.filter((option) => option !== lead)
        return (
          <div className="flex flex-col gap-3">
            {lead && (
              <Button
                key={lead.key}
                data-primary
                size="xl"
                fullWidth
                variant={lead.key === 'done' ? 'secondary' : 'primary'}
                disabled={lead.disabled}
                onClick={() => handleConsume(lead)}
              >
                {lead.label}
              </Button>
            )}
            {rest.length > 0 && (
              <div
                className="grid gap-3"
                style={{ gridTemplateColumns: `repeat(${rest.length}, minmax(0, 1fr))` }}
              >
                {rest.map((option) => (
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
            )}
            {onEdit && (
              <Button size="lg" variant="ghost" fullWidth onClick={onEdit}>
                Edit item
              </Button>
            )}
          </div>
        )
      })()}
    </BottomSheet>
  )
}

export default ConsumptionSheet
