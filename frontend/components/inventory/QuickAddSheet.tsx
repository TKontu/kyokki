'use client'

/**
 * QuickAddSheet Component
 * "+ Add" on the home page: find a generic product or create one, then add stock in one call.
 */

import React, { useMemo, useState } from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import { fieldErrorClass, fieldInputClass, fieldLabelClass } from '@/components/ui/formStyles'
import { useCategories } from '@/hooks/useCategories'
import { useQuickAddInventoryItem } from '@/hooks/useInventory'
import { useProductSearch } from '@/hooks/useProducts'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { formatQuantity } from '@/lib/consumption'
import { addDaysISO } from '@/lib/dates'
import { locationOptions } from '@/lib/stock'
import type { Category } from '@/types/category'
import type { InventoryLocation, QuickAddRequest, Unit } from '@/types/inventory'
import type { ProductMaster } from '@/types/product'

export interface QuickAddSheetProps {
  open: boolean
  onClose: () => void
}

type Selection = { kind: 'existing'; product: ProductMaster } | { kind: 'new'; name: string }

const UNITS: Unit[] = ['pcs', 'g', 'dl', 'tsp', 'tbsp']

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
  const [quantity, setQuantity] = useState('1')
  const [unit, setUnit] = useState<Unit>('pcs')
  // A plain string: a product may name a storage type this build does not know (H04)
  const [location, setLocation] = useState<string>('main_fridge')
  const [expiry, setExpiry] = useState('')
  const [expiryTouched, setExpiryTouched] = useState(false)

  const search = useProductSearch(term)
  const trimmed = term.trim()
  const results = trimmed ? (search.data ?? []) : []
  const exactMatch = results.some(
    (product) => product.canonical_name.toLowerCase() === trimmed.toLowerCase()
  )

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
    setQuantity(String(product.default_quantity ?? 1))
    setUnit(product.default_unit)
    setLocation(locationFor(product.storage_type))
    setExpiry(addDaysISO(product.default_shelf_life_days))
    setExpiryTouched(false)
  }

  const pickNew = () => {
    setSelection({ kind: 'new', name: trimmed })
    setCategoryId(null)
    setQuantity('1')
    setUnit('pcs')
    setLocation('main_fridge')
    setExpiry('')
    setExpiryTouched(false)
  }

  const pickCategory = (category: Category) => {
    setCategoryId(category.id)
    setLocation(locationFor(category.default_storage))
    if (!expiryTouched) {
      setExpiry(addDaysISO(category.default_shelf_life_days))
    }
  }

  const amount = Number(quantity)
  const quantityValid = quantity.trim() !== '' && Number.isFinite(amount) && amount > 0
  const needsCategory = selection?.kind === 'new' && !categoryId
  const canAdd = selection !== null && quantityValid && !needsCategory && !quickAdd.isPending

  const submit = () => {
    if (!selection || !canAdd) return
    const productName =
      selection.kind === 'existing' ? selection.product.canonical_name : selection.name
    const payload: QuickAddRequest = {
      ...(selection.kind === 'existing'
        ? { product_id: selection.product.id }
        : { name: selection.name, category: categoryId ?? undefined }),
      quantity: amount,
      unit,
      location,
      ...(expiryTouched && expiry ? { expiry_date: expiry } : {}),
    }

    quickAdd.mutate(payload, {
      onSuccess: (item) => {
        toast.success(`Added ${formatQuantity(amount)} ${unit} · ${item.product_name}`)
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
        <label htmlFor="quick-add-search" className={fieldLabelClass}>
          Product
        </label>
        <input
          id="quick-add-search"
          type="search"
          autoComplete="off"
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Milk, ground beef, apples…"
          className={`${fieldInputClass} mt-1`}
        />
        <ul className="mt-3 flex flex-col gap-2">
          {results.map((product) => (
            <li key={product.id}>
              <button
                type="button"
                aria-label={product.canonical_name}
                onClick={() => pickExisting(product)}
                className="flex w-full min-h-touch items-center gap-2 rounded-ui border border-ui-border dark:border-ui-dark-border px-3 text-left text-ui-text dark:text-ui-dark-text"
              >
                <span aria-hidden="true">{categoryById.get(product.category)?.icon ?? ''}</span>
                {product.canonical_name}
              </button>
            </li>
          ))}
          {trimmed && !exactMatch && (
            <li>
              <button
                type="button"
                onClick={pickNew}
                className="flex w-full min-h-touch items-center rounded-ui border border-dashed border-ui-border dark:border-ui-dark-border px-3 text-left text-ui-text dark:text-ui-dark-text"
              >
                {`Create new: ${trimmed}`}
              </button>
            </li>
          )}
        </ul>
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
          <Button size="lg" disabled={!canAdd} loading={quickAdd.isPending} onClick={submit}>
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

        <div>
          <label htmlFor="quick-add-quantity" className={fieldLabelClass}>
            Quantity
          </label>
          <input
            id="quick-add-quantity"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          {!quantityValid && (
            <p role="alert" className={fieldErrorClass}>
              Enter a quantity above 0
            </p>
          )}
        </div>

        <ChoiceGroup
          label="Unit"
          name="quick-add-unit"
          className="grid-cols-5"
          value={unit}
          options={UNITS.map((option) => ({ value: option, label: option }))}
          onChange={setUnit}
        />

        <ChoiceGroup
          label="Location"
          name="quick-add-location"
          value={location}
          options={locationOptions(location)}
          onChange={setLocation}
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
