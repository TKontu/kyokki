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
import { ProductEditSheet } from '@/components/products/ProductEditSheet'
import { useDeleteInventoryItem, useUpdateInventoryItem } from '@/hooks/useInventory'
import { useProduct } from '@/hooks/useProducts'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { formatQuantity } from '@/lib/consumption'
import { isInactive, locationOptions } from '@/lib/stock'
import type { InventoryItem, InventoryItemUpdate } from '@/types/inventory'

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
  // A plain string: the item may already sit in a location this build does not know (H04)
  const [location, setLocation] = useState<string>(item.location)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [editingProduct, setEditingProduct] = useState(false)
  const product = useProduct(editingProduct ? item.product_master_id : null)

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
          {`Delete ${name}? This removes the item; what it wasted stays on Gone. Use Mark as gone if it was thrown away.`}
        </p>
      </BottomSheet>
    )
  }

  if (editingProduct) {
    return product.data ? (
      <ProductEditSheet
        product={product.data}
        onClose={() => setEditingProduct(false)}
      />
    ) : null
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
          <div className="grid grid-cols-2 gap-3">
            {!isInactive(item) && (
              <Button
                variant="secondary"
                size="lg"
                disabled={busy}
                // The way back from a mis-tap is the header's Undo, which names what it reverses
                // and does not vanish after a few seconds (2026-09-22)
                onClick={() => patch({ status: 'discarded' }, `Marked as gone · ${name}`)}
              >
                Mark as gone
              </Button>
            )}
            {isInactive(item) && (
              // The sheet has always rendered a one-column footer for a gone item; this is
              // what belongs in it. Reachable once a list shows inactive items - until then
              // the header's Undo is the way back.
              <Button
                variant="secondary"
                size="lg"
                disabled={busy}
                onClick={() =>
                  patch({ status: 'opened' }, `Back in the kitchen · ${name}`)
                }
              >
                Put it back
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

        {/* A wrong expiry is usually the product's shelf life, not this item's date,
            and until H18 there was no way to correct it. */}
        <div>
          <Button variant="ghost" size="sm" onClick={() => setEditingProduct(true)}>
            {`Edit ${name}…`}
          </Button>
        </div>

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
          options={locationOptions(item.location)}
          onChange={setLocation}
        />
        {/* Q12/DEC-10: freezing restarts the clock, and taking it back out deliberately
            does not - nothing records when it went in, and thawed food keeps for a day
            or two whatever it was. Say both, because a date that moves on its own is
            alarming and one that does not move is worse. */}
        {location === 'freezer' && item.location !== 'freezer' && (
          <p className="mt-2 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {expiry === item.expiry_date.split('T')[0]
              ? 'Saving will give this a freezer date. Taking it back out later will not change it back — set the date yourself then.'
              : 'Your date will be kept, not the freezer one.'}
          </p>
        )}
      </div>
    </BottomSheet>
  )
}

export function ItemEditSheet({ item, open, onClose }: ItemEditSheetProps) {
  // Mount the form only while open, so it starts from the item's current values each time.
  return open && item ? <ItemEditForm item={item} onClose={onClose} /> : null
}

export default ItemEditSheet
