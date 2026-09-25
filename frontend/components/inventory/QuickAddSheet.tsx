'use client'

/**
 * QuickAddSheet Component
 * "+ Add" on the home page: find a generic product or create one, then add stock in one call.
 *
 * No amount (V2, operator ask 2026-09-24: presence, not amounts). The backend still stores one,
 * so the request carries the product's usual amount and unit, or one piece for a new product.
 */

import React, { useMemo, useState } from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import { fieldInputClass, fieldLabelClass } from '@/components/ui/formStyles'
import { useCategories } from '@/hooks/useCategories'
import { useQuickAddInventoryItem } from '@/hooks/useInventory'
import { ProductSearch } from '@/components/products/ProductSearch'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { addDaysISO } from '@/lib/dates'
import { locationOptions } from '@/lib/stock'
import type { Category } from '@/types/category'
import type { InventoryLocation, QuickAddRequest } from '@/types/inventory'
import type { ProductMaster } from '@/types/product'

export interface QuickAddSheetProps {
  open: boolean
  onClose: () => void
}

type Selection = { kind: 'existing'; product: ProductMaster } | { kind: 'new'; name: string }

const STORAGE_LOCATION: Partial<Record<string, InventoryLocation>> = {
  refrigerator: 'main_fridge',
  freezer: 'freezer',
  pantry: 'pantry',
}

/**
 * Where a product of this storage type lives. A storage type this build does not know keeps its
 * own name as the location, so the Location group still has something checked and `submit`
 * still sends a value; without it the group was blank and the payload carried `undefined` (H04).
 */
function locationFor(storageType: string): string {
  return STORAGE_LOCATION[storageType] ?? storageType
}

function QuickAddForm({ onClose }: { onClose: () => void }) {
  const toast = useToast()
  const quickAdd = useQuickAddInventoryItem()
  const categories = useCategories()

  const [term, setTerm] = useState('')
  const [selection, setSelection] = useState<Selection | null>(null)
  const [categoryId, setCategoryId] = useState<string | null>(null)
  // Whether the location is the cook's answer or the sheet's guess (H25): a typed name may
  // resolve to a product the client has never seen, whose own shelf is the right one - so a
  // guess is left out of the request rather than sent as if it were chosen.
  const [locationChosen, setLocationChosen] = useState(false)
  // A plain string: a product may name a storage type this build does not know (H04)
  const [location, setLocation] = useState<string>('main_fridge')
  const [expiry, setExpiry] = useState('')
  const [expiryTouched, setExpiryTouched] = useState(false)

  const sortedCategories = useMemo(
    () => [...(categories.data ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [categories.data]
  )
  const categoryById = useMemo(
    () => new Map((categories.data ?? []).map((category) => [category.id, category])),
    [categories.data]
  )

  const pickExisting = (product: ProductMaster) => {
    setSelection({ kind: 'existing', product })
    setLocationChosen(true)
    setLocation(locationFor(product.storage_type))
    setExpiry(addDaysISO(product.default_shelf_life_days))
    setExpiryTouched(false)
  }

  const pickNew = (name: string) => {
    setSelection({ kind: 'new', name })
    setCategoryId(null)
    setLocationChosen(false)
    setLocation('main_fridge')
    setExpiry('')
    setExpiryTouched(false)
  }

  const pickCategory = (category: Category) => {
    setCategoryId(category.id)
    // The category's shelf is a default to show, not an answer to send: the server derives the
    // same one, and would derive a better one if the name resolves to an existing product.
    setLocation(locationFor(category.default_storage))
    if (!expiryTouched) {
      setExpiry(addDaysISO(category.default_shelf_life_days))
    }
  }

  const needsCategory = selection?.kind === 'new' && !categoryId
  const canAdd = selection !== null && !needsCategory && !quickAdd.isPending

  const submit = () => {
    if (!selection || !canAdd) return
    const productName =
      selection.kind === 'existing' ? selection.product.canonical_name : selection.name
    // The backend still keeps an amount: the product's usual one, else one piece. A new
    // product sends no unit, so the server's own default applies.
    const payload: QuickAddRequest = {
      ...(selection.kind === 'existing'
        ? {
            product_id: selection.product.id,
            quantity: selection.product.default_quantity ?? 1,
            unit: selection.product.default_unit,
          }
        : { name: selection.name, category: categoryId ?? undefined, quantity: 1 }),
      ...(locationChosen ? { location } : {}),
      ...(expiryTouched && expiry ? { expiry_date: expiry } : {}),
    }

    quickAdd.mutate(payload, {
      onSuccess: (item) => {
        toast.success(`Added · ${item.product_name}`)
        onClose()
      },
      onError: (error) => {
        // Keep the sheet open so nothing typed is lost; 4xx messages are meant for people.
        const clientError = isAPIError(error) && error.status < 500 && error.message
        toast.error(clientError ? error.message : `Could not add ${productName}`)
      },
    })
  }

  if (!selection) {
    return (
      <BottomSheet open onClose={onClose} title="Add to stock">
        {/* The same control the receipt review row uses (H15). */}
        <ProductSearch
          categories={categories.data ?? []}
          inputId="quick-add-search"
          term={term}
          onTermChange={setTerm}
          onPickExisting={pickExisting}
          onPickNew={pickNew}
        />
      </BottomSheet>
    )
  }

  const title = selection.kind === 'existing' ? selection.product.canonical_name : selection.name

  return (
    <BottomSheet
      open
      onClose={onClose}
      title={title}
      footer={
        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" size="lg" onClick={() => setSelection(null)}>
            Back
          </Button>
          <Button data-primary size="lg" disabled={!canAdd} loading={quickAdd.isPending} onClick={submit}>
            Add
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {selection.kind === 'new' && (
          <>
            <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
              New product
            </p>
            <div>
              <span className={fieldLabelClass} aria-hidden="true">
                Category
              </span>
              <div className="mt-1">
                <ChoiceGroup
                  label="Category"
                  name="quick-add-category"
                  className="grid-cols-2 sm:grid-cols-3"
                  value={categoryId}
                  options={sortedCategories.map((category) => ({
                    value: category.id,
                    label: `${category.icon ?? ''} ${category.display_name}`.trim(),
                  }))}
                  onChange={(id) => {
                    const category = categoryById.get(id)
                    if (category) pickCategory(category)
                  }}
                />
              </div>
            </div>
          </>
        )}

        <ChoiceGroup
          label="Location"
          name="quick-add-location"
          value={location}
          options={locationOptions(location)}
          onChange={(next) => {
            setLocationChosen(true)
            setLocation(next)
          }}
        />

        <div>
          <label htmlFor="quick-add-expiry" className={fieldLabelClass}>
            Expiry
          </label>
          <input
            id="quick-add-expiry"
            type="date"
            value={expiry}
            onChange={(event) => {
              setExpiry(event.target.value)
              setExpiryTouched(true)
            }}
            className={`${fieldInputClass} mt-1`}
          />
        </div>
      </div>
    </BottomSheet>
  )
}

export function QuickAddSheet({ open, onClose }: QuickAddSheetProps) {
  // Mount the form only while open: it starts empty each time and fetches nothing when closed.
  return open ? <QuickAddForm onClose={onClose} /> : null
}

export default QuickAddSheet
