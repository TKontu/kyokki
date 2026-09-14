'use client'

/**
 * ItemEditSheet Component
 * "Edit" on a stock card: correct quantity, expiry and location, mark as gone, or delete.
 * Quantity changes are corrections, not consumption (MVP-S4 ruling); Consume records use.
 */

import React, { useState } from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import {
  fieldErrorClass,
  fieldHintClass,
  fieldInputClass,
  fieldLabelClass,
} from '@/components/ui/formStyles'
import { useDeleteInventoryItem, useUpdateInventoryItem } from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { formatQuantity } from '@/lib/consumption'
import { LOCATION_OPTIONS, isInactive } from '@/lib/stock'
import type { InventoryItem, InventoryItemUpdate, InventoryLocation } from '@/types/inventory'

export interface ItemEditSheetProps {
  item: InventoryItem | null
  open: boolean
  onClose: () => void
}

function errorText(error: unknown, fallback: string): string {
  // 4xx messages come from the API and are meant for people; server and network failures are not
  return isAPIError(error) && error.status < 500 && error.message ? error.message : fallback
}

function ItemEditForm({ item, onClose }: { item: InventoryItem; onClose: () => void }) {
  const toast = useToast()
  const update = useUpdateInventoryItem()
  const remove = useDeleteInventoryItem()

  const [quantity, setQuantity] = useState(String(item.current_quantity))
  const [expiry, setExpiry] = useState(item.expiry_date.split('T')[0])
  const [location, setLocation] = useState<InventoryLocation>(item.location)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const name = item.product_name
  const amount = Number(quantity)
  const quantityValid = quantity.trim() !== '' && Number.isFinite(amount) && amount >= 0

  const changes: InventoryItemUpdate = {}
  if (quantityValid && amount !== item.current_quantity) changes.current_quantity = amount
  if (expiry && expiry !== item.expiry_date.split('T')[0]) changes.expiry_date = expiry
  if (location !== item.location) changes.location = location
  const busy = update.isPending || remove.isPending
  const canSave = quantityValid && Object.keys(changes).length > 0 && !busy

  const patch = (data: InventoryItemUpdate, success: string) => {
    update.mutate(
      { id: item.id, data },
      {
        onSuccess: () => {
          toast.success(success)
          onClose()
        },
        onError: (error) => toast.error(errorText(error, `Could not save ${name}`)),
      }
    )
  }

  const confirmDelete = () => {
    remove.mutate(item.id, {
      onSuccess: () => {
        toast.success(`Deleted · ${name}`)
        onClose()
      },
      onError: (error) => toast.error(errorText(error, `Could not delete ${name}`)),
    })
  }

  const subtitle = [item.category_name, item.purchase_date && `Added ${item.purchase_date}`]
    .filter(Boolean)
    .join(' · ')

  if (confirmingDelete) {
    return (
      <BottomSheet
        open
        onClose={onClose}
        title={name}
        footer={
          <div className="grid grid-cols-2 gap-3">
            <Button variant="secondary" size="lg" onClick={() => setConfirmingDelete(false)}>
              Cancel
            </Button>
            <Button variant="danger" size="lg" loading={remove.isPending} onClick={confirmDelete}>
              Yes, delete
            </Button>
          </div>
        }
      >
        <p className="text-base text-ui-text dark:text-ui-dark-text">
          {`Delete ${name}? This removes the item and its history. Use Mark as gone if it was thrown away.`}
        </p>
      </BottomSheet>
    )
  }

  return (
    <BottomSheet
      open
      onClose={onClose}
      title={name}
      footer={
        <div className="flex flex-col gap-3">
          <Button size="lg" fullWidth disabled={!canSave} loading={update.isPending} onClick={() => patch(changes, `Saved · ${name}`)}>
            Save
          </Button>
          <div className={`grid gap-3 ${isInactive(item) ? 'grid-cols-1' : 'grid-cols-2'}`}>
            {!isInactive(item) && (
              <Button
                variant="secondary"
                size="lg"
                disabled={busy}
                onClick={() => patch({ status: 'discarded' }, `Marked as gone · ${name}`)}
              >
                Mark as gone
              </Button>
            )}
            <Button variant="danger" size="lg" disabled={busy} onClick={() => setConfirmingDelete(true)}>
              Delete
            </Button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {subtitle && (
          <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">{subtitle}</p>
        )}

        <div>
          <label htmlFor="item-edit-quantity" className={fieldLabelClass}>
            {`Quantity (${item.unit})`}
          </label>
          <input
            id="item-edit-quantity"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          {quantityValid ? (
            <p className={fieldHintClass}>
              {`0 marks it used up. More than ${formatQuantity(item.initial_quantity)} ${item.unit} raises the full amount.`}
            </p>
          ) : (
            <p role="alert" className={fieldErrorClass}>
              Enter 0 or more
            </p>
          )}
        </div>

        <div>
          <label htmlFor="item-edit-expiry" className={fieldLabelClass}>
            Expiry
          </label>
          <input
            id="item-edit-expiry"
            type="date"
            value={expiry}
            onChange={(event) => setExpiry(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
        </div>

        <ChoiceGroup
          label="Location"
          name="item-edit-location"
          value={location}
          options={LOCATION_OPTIONS}
          onChange={setLocation}
        />
      </div>
    </BottomSheet>
  )
}

export function ItemEditSheet({ item, open, onClose }: ItemEditSheetProps) {
  // Mount the form only while open, so it starts from the item's current values each time.
  return open && item ? <ItemEditForm item={item} onClose={onClose} /> : null
}

export default ItemEditSheet
