'use client'

/**
 * ItemEditSheet Component
 * "Edit" behind a tile's "…": correct expiry and location, mark as gone, or delete. No amount:
 * the UI tracks presence, not quantities (V2, operator ask 2026-09-24); "Used up" is on the
 * item sheet and a tile tap.
 *
 * The category belongs to the product, not the item, so it shows here with a way to change
 * it: both "Change…" and "Change product details…" open the product's sheet (Q25).
 */

import React, { useState } from 'react'
import Link from 'next/link'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import { fieldInputClass, fieldLabelClass } from '@/components/ui/formStyles'
import { ProductEditSheet } from '@/components/products/ProductEditSheet'
import { FieldMoved } from '@/components/ui/FieldMoved'
import { useDeleteInventoryItem, useUpdateInventoryItem } from '@/hooks/useInventory'
import { useFieldEdit } from '@/hooks/useFieldEdit'
import { useItemSource } from '@/hooks/useItemSource'
import { useProduct } from '@/hooks/useProducts'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { displayName } from '@/lib/displayName'
import { formatDate, useT } from '@/lib/i18n'
import { useLanguage } from '@/lib/language'
import { receiptDate, storeName } from '@/lib/receipts'
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

  const expiryField = useFieldEdit(item.expiry_date.split('T')[0])
  // A plain string: the item may already sit in a location this build does not know (H04)
  const locationField = useFieldEdit(item.location)
  const expiry = expiryField.value
  const location = locationField.value
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [editingProduct, setEditingProduct] = useState(false)
  const product = useProduct(editingProduct ? item.product_master_id : null)
  // Nothing to fetch for a hand-added item (Q26): it has no receipt to ask about.
  const source = useItemSource(item.receipt_id ? item.id : null)

  const [language] = useLanguage()
  const { t } = useT()
  const name = displayName(item.product_display_names, item.product_name, language)

  // Only what the cook touched and actually changed: what moved underneath is not theirs
  const changes: InventoryItemUpdate = {}
  if (expiry && expiryField.changed) changes.expiry_date = expiry
  if (locationField.changed) changes.location = location
  const busy = update.isPending || remove.isPending
  const canSave = Object.keys(changes).length > 0 && !busy

  const patch = (data: InventoryItemUpdate, success: string) => {
    update.mutate(
      { id: item.id, data },
      {
        onSuccess: () => {
          toast.success(success)
          onClose()
        },
        onError: (error) => toast.error(errorText(error, t('inventory.itemEdit.saveError', { name }))),
      }
    )
  }

  const confirmDelete = () => {
    remove.mutate(item.id, {
      onSuccess: () => {
        toast.success(t('inventory.itemEdit.deletedToast', { name }))
        onClose()
      },
      onError: (error) => toast.error(errorText(error, t('inventory.itemEdit.deleteError', { name }))),
    })
  }

  const subtitle = item.purchase_date
    ? t('inventory.itemEdit.addedOn', { date: formatDate(item.purchase_date, language) })
    : ''
  const editProduct = () => setEditingProduct(true)

  if (confirmingDelete) {
    return (
      <BottomSheet
        open
        onClose={onClose}
        title={name}
        footer={
          <div className="grid grid-cols-2 gap-3">
            {/* The safe one is focused, so Enter on a confirm never deletes (H45) */}
            <Button data-primary variant="secondary" size="lg" onClick={() => setConfirmingDelete(false)}>
              {t('inventory.itemEdit.cancel')}
            </Button>
            <Button variant="danger" size="lg" loading={remove.isPending} onClick={confirmDelete}>
              {t('inventory.itemEdit.confirmDelete')}
            </Button>
          </div>
        }
      >
        <p className="text-base text-ui-text dark:text-ui-dark-text">
          {t('inventory.itemEdit.deleteBody', { name })}
        </p>
      </BottomSheet>
    )
  }

  if (editingProduct) {
    if (product.data) {
      return <ProductEditSheet product={product.data} onClose={() => setEditingProduct(false)} />
    }
    // Never a blank screen: say what is happening, and on a failure lead back to the item
    return (
      <BottomSheet
        open
        onClose={onClose}
        title={name}
        footer={
          product.isError ? (
            <Button data-primary variant="secondary" size="lg" fullWidth onClick={() => setEditingProduct(false)}>
              {t('inventory.itemEdit.backTo', { name })}
            </Button>
          ) : undefined
        }
      >
        {product.isError ? (
          <p role="alert" className="text-base text-red-600 dark:text-red-400">
            {t('inventory.itemEdit.productDetailsError', { name })}
          </p>
        ) : (
          <p className="text-base text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {t('inventory.itemEdit.loadingProductDetails')}
          </p>
        )}
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
          <Button
            data-primary
            size="lg"
            fullWidth
            disabled={!canSave}
            loading={update.isPending}
            onClick={() => patch(changes, t('inventory.itemEdit.savedToast', { name }))}
          >
            {t('inventory.itemEdit.save')}
          </Button>
          <div className="grid grid-cols-2 gap-3">
            {!isInactive(item) && (
              <Button
                variant="secondary"
                size="lg"
                disabled={busy}
                // The way back from a mis-tap is the header's Undo, which names what it reverses
                // and does not vanish after a few seconds (2026-09-22)
                onClick={() =>
                  patch({ status: 'discarded' }, t('inventory.itemEdit.markedGoneToast', { name }))
                }
              >
                {t('inventory.itemEdit.markAsGone')}
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
                  patch({ status: 'opened' }, t('inventory.itemEdit.backInKitchenToast', { name }))
                }
              >
                {t('inventory.itemEdit.putItBack')}
              </Button>
            )}
            <Button variant="danger" size="lg" disabled={busy} onClick={() => setConfirmingDelete(true)}>
              {t('inventory.itemEdit.delete')}
            </Button>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {subtitle && (
          <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">{subtitle}</p>
        )}

        {/* Where this item came from (Q26): traces "fish soup" back to the printed receipt
            line it was confirmed from, and links to the receipt's audit view. The store name
            and date are the receipt's own text (never translated); only the surrounding
            words follow the chosen language. */}
        {source.data && (
          <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            <Link href={`/receipts/${source.data.receipt_id}`} className="underline">
              {source.data.line_text
                ? t('inventory.itemEdit.fromLineAndText', {
                    store: storeName(source.data),
                    date: receiptDate(source.data),
                    line: source.data.line_text,
                  })
                : t('inventory.itemEdit.fromLine', {
                    store: storeName(source.data),
                    date: receiptDate(source.data),
                  })}
            </Link>
          </p>
        )}

        {/* The category is the product's, so it is changed on the product's sheet (Q25). A new
            category re-dates only the items whose date came from the old category's
            placeholder shelf life; a date the product or the cook set stays. */}
        <div className="flex items-center justify-between gap-3">
          <p className="text-base text-ui-text dark:text-ui-dark-text">
            {t('inventory.itemEdit.categoryLine', {
              category: item.category_name || t('inventory.itemEdit.noCategory'),
            })}
          </p>
          {/* Held while a save is in flight: its success closes this sheet, and would take the
              product's sheet with it mid-edit */}
          <Button variant="secondary" size="md" disabled={busy} onClick={editProduct}>
            {t('inventory.itemEdit.change')}
          </Button>
        </div>

        {/* A wrong expiry is usually the product's shelf life, not this item's date,
            and until H18 there was no way to correct it. */}
        <div>
          <Button variant="ghost" size="md" disabled={busy} onClick={editProduct}>
            {t('inventory.itemEdit.changeProductDetails')}
          </Button>
        </div>

        <div>
          <label htmlFor="item-edit-expiry" className={fieldLabelClass}>
            {t('inventory.itemEdit.expiry')}
          </label>
          <input
            id="item-edit-expiry"
            type="date"
            value={expiry}
            onChange={(event) => expiryField.set(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          <FieldMoved label={t('inventory.itemEdit.expiry')} field={expiryField} />
        </div>

        <ChoiceGroup
          label={t('inventory.itemEdit.location')}
          name="item-edit-location"
          value={location}
          options={locationOptions(item.location, language)}
          onChange={locationField.set}
        />
        <FieldMoved label={t('inventory.itemEdit.location')} field={locationField} />
        {/* Q12/DEC-10: freezing restarts the clock, and taking it back out deliberately
            does not - nothing records when it went in, and thawed food keeps for a day
            or two whatever it was. Say both, because a date that moves on its own is
            alarming and one that does not move is worse. */}
        {location === 'freezer' && item.location !== 'freezer' && (
          <p className="mt-2 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {expiry === item.expiry_date.split('T')[0]
              ? t('inventory.itemEdit.freezerDateNote')
              : t('inventory.itemEdit.freezerKeptNote')}
          </p>
        )}
      </div>
    </BottomSheet>
  )
}

export function ItemEditSheet({ item, open, onClose }: ItemEditSheetProps) {
  // Mount the form only while open, so it starts from the item's current values each time.
  // Keyed by item: the form's fields follow the item they were opened on, and a sheet that
  // ever swapped items in place would start clean rather than inherit the last one's edits.
  return open && item ? <ItemEditForm key={item.id} item={item} onClose={onClose} /> : null
}

export default ItemEditSheet
