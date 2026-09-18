'use client'

/**
 * ReceiptItemRow
 * One read receipt line on the review screen: include it or skip it, fix the name, amount and
 * category. A line already matched to a product keeps that product and needs no category.
 */

import React, { useState } from 'react'
import { ProductSearch } from '@/components/products/ProductSearch'
import { ProvenanceChip } from '@/components/receipts/ProvenanceChip'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import {
  fieldErrorClass,
  fieldInputClass,
  fieldLabelClass,
} from '@/components/ui/formStyles'
import type { Category } from '@/types/category'
import type { ExtractedItem, ReceiptUnit } from '@/types/receipt'

/** What the review screen holds for one line while it is being edited. */
export interface ReviewRow {
  index: number
  include: boolean
  name: string
  category: string
  quantity: string
  unit: ReceiptUnit
  /**
   * The product the cook chose on this row, overriding what was proposed.
   * `null` means detached: treat the line as a new product named by `name` (H15).
   * `undefined` means untouched - whatever the read proposed still stands.
   */
  productId?: string | null
  productName?: string | null
}

export interface ReceiptItemRowProps {
  item: ExtractedItem
  row: ReviewRow
  categories: Category[]
  onChange: (changes: Partial<ReviewRow>) => void
}

const UNITS: ReceiptUnit[] = ['pcs', 'g', 'dl']

/** The product this row will actually use: the cook's choice, else what was read. */
export function chosenProductId(item: ExtractedItem, row: ReviewRow): string | null {
  return row.productId === undefined ? item.product_id : row.productId
}

/** A line can be added once it has a product to go to: a match, or a name and a category. */
export function canInclude(item: ExtractedItem, row: ReviewRow): boolean {
  if (chosenProductId(item, row)) return true
  return row.name.trim() !== '' && row.category !== ''
}

/**
 * The shop weighed it, we are counting it (Q2). Showing both keeps the conversion honest,
 * and the quantity and unit below are already editable if the guess is wrong.
 */
function describeConversion(item: ExtractedItem): string | null {
  if (item.printed_quantity == null || item.printed_unit == null) return null
  const printed =
    item.printed_unit === 'g' && item.printed_quantity >= 1000
      ? `${(item.printed_quantity / 1000).toFixed(3).replace(/0+$/, '').replace(/\.$/, '')} kg`
      : `${item.printed_quantity} ${item.printed_unit}`
  return `${printed} → ${item.quantity} ${item.unit}`
}

export function ReceiptItemRow({ item, row, categories, onChange }: ReceiptItemRowProps) {
  const [changing, setChanging] = useState(false)
  const [searchTerm, setSearchTerm] = useState(row.name)
  const productId = chosenProductId(item, row)
  const matched = Boolean(productId)
  const ready = canInclude(item, row)
  const rowId = `row-${item.index}`
  const conversion = describeConversion(item)
  const productName =
    row.productName !== undefined ? row.productName : item.product_name
  // The cook's own choice is their word, whatever the read proposed.
  const chosenByCook = row.productId !== undefined

  return (
    <div
      className={`rounded-ui border p-3 ${
        row.include
          ? 'border-ui-border dark:border-ui-dark-border'
          : 'border-dashed border-ui-border dark:border-ui-dark-border opacity-60'
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          id={`${rowId}-include`}
          checked={row.include}
          disabled={!ready}
          onChange={(event) => onChange({ include: event.target.checked })}
          aria-label={`Include ${row.name || item.name}`}
          className="mt-3 h-6 w-6 shrink-0"
        />
        <div className="flex-1">
          {matched ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-base font-medium text-ui-text dark:text-ui-dark-text">
                {`→ ${productName ?? ''}`}
              </p>
              <ProvenanceChip
                source={chosenByCook ? 'alias' : item.match_source}
                verified={chosenByCook || item.verified}
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setChanging(true)}
                aria-label={`Change ${productName ?? item.name}`}
              >
                Change
              </Button>
            </div>
          ) : (
            <>
              <label htmlFor={`${rowId}-name`} className={`${fieldLabelClass} sr-only`}>
                Product name
              </label>
              <input
                id={`${rowId}-name`}
                type="text"
                aria-label="Product name"
                value={row.name}
                onChange={(event) => onChange({ name: event.target.value })}
                className={fieldInputClass}
              />
              {!changing && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-1"
                  onClick={() => setChanging(true)}
                  aria-label={`Find a product for ${item.name}`}
                >
                  Find existing product
                </Button>
              )}
            </>
          )}
          {changing && (
            <div className="mt-2 rounded-ui border border-ui-border dark:border-ui-dark-border p-3">
              <ProductSearch
                categories={categories}
                inputId={`${rowId}-search`}
                term={searchTerm}
                onTermChange={setSearchTerm}
                newLabel={(term) => `New product: ${term}`}
                onPickExisting={(product) => {
                  onChange({
                    productId: product.id,
                    productName: product.canonical_name,
                    name: product.canonical_name,
                  })
                  setChanging(false)
                }}
                onPickNew={(name) => {
                  // Detach: the line becomes a new product named here, and confirm
                  // learns the printed name against it (H15).
                  onChange({ productId: null, productName: null, name })
                  setChanging(false)
                }}
              />
              <Button
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => setChanging(false)}
              >
                Cancel
              </Button>
            </div>
          )}
          <p className="mt-1 text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
            {item.name}
            {conversion && <span>{` · ${conversion}`}</span>}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="w-24">
          <label htmlFor={`${rowId}-quantity`} className={fieldLabelClass}>
            Quantity
          </label>
          <input
            id={`${rowId}-quantity`}
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            aria-label="Quantity"
            value={row.quantity}
            onChange={(event) => onChange({ quantity: event.target.value })}
            className={`${fieldInputClass} mt-1`}
          />
        </div>

        <div className="w-44">
          <ChoiceGroup
            label="Unit"
            name={`${rowId}-unit`}
            className="grid-cols-3"
            value={row.unit}
            options={UNITS.map((unit) => ({ value: unit, label: unit }))}
            onChange={(unit) => onChange({ unit })}
          />
        </div>

        {!matched && (
          <div className="min-w-48 flex-1">
            <label htmlFor={`${rowId}-category`} className={fieldLabelClass}>
              Category
            </label>
            <select
              id={`${rowId}-category`}
              aria-label="Category"
              value={row.category}
              onChange={(event) => onChange({ category: event.target.value })}
              className={`${fieldInputClass} mt-1`}
            >
              <option value="">Pick a category…</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {`${category.icon ?? ''} ${category.display_name}`.trim()}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!ready && (
        <p className={fieldErrorClass}>
          {row.name.trim() === ''
            ? 'Give this product a name to include it'
            : 'Pick a category to include it'}
        </p>
      )}
    </div>
  )
}

export default ReceiptItemRow
