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
import {
  fieldErrorClass,
  fieldInputClass,
  fieldLabelClass,
} from '@/components/ui/formStyles'
import { useReanalyseLine } from '@/hooks/useReceipts'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
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
  /** The receipt this row belongs to, for the re-analyse request (Q38). */
  receiptId: string
  /** The cook has edited this row by hand since it loaded: a re-analyse asks before it overwrites. */
  dirty: boolean
  /** A re-analyse answered; the caller applies it to the row (and clears its own edits). */
  onReanalysed: (item: ExtractedItem) => void
}


/** The product this row will actually use: the cook's choice, else what was read. */
export function chosenProductId(item: ExtractedItem, row: ReviewRow): string | null {
  return row.productId === undefined ? item.product_id : row.productId
}

/** A line can be added once it has a product to go to: a match, or a name and a category. */
export function canInclude(item: ExtractedItem, row: ReviewRow): boolean {
  if (chosenProductId(item, row)) return true
  return row.name.trim() !== '' && row.category !== ''
}

export function ReceiptItemRow({
  item,
  row,
  categories,
  onChange,
  receiptId,
  dirty,
  onReanalysed,
}: ReceiptItemRowProps) {
  const [changing, setChanging] = useState(false)
  const [searchTerm, setSearchTerm] = useState(row.name)
  const [reanalysing, setReanalysing] = useState(false)
  const [hint, setHint] = useState('')
  const toast = useToast()
  const reanalyse = useReanalyseLine()
  const productId = chosenProductId(item, row)
  const matched = Boolean(productId)
  const ready = canInclude(item, row)
  const rowId = `row-${item.index}`
  const productName =
    row.productName !== undefined ? row.productName : item.product_name
  // The cook's own choice is their word, whatever the read proposed.
  const chosenByCook = row.productId !== undefined

  const askAgain = () => {
    if (!item.line_id) return
    reanalyse.mutate(
      { receiptId, lineId: item.line_id, hint: hint.trim() || null },
      {
        onSuccess: (updated) => {
          if (
            dirty &&
            !window.confirm(
              'This row has been edited by hand. Replace it with the re-analysed result?'
            )
          ) {
            return
          }
          onReanalysed(updated)
          setReanalysing(false)
          setHint('')
        },
        onError: (error) => {
          toast.error(
            isAPIError(error) ? error.message : 'Could not re-analyse this line'
          )
        },
      }
    )
  }

  return (
    <div
      aria-busy={reanalyse.isPending}
      className={`rounded-ui border p-3 ${
        row.include
          ? 'border-ui-border dark:border-ui-dark-border'
          : 'border-dashed border-ui-border dark:border-ui-dark-border opacity-60'
      } ${reanalyse.isPending ? 'opacity-70' : ''}`}
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
          {/* The printed line, never editable and never replaced by the generic name
              above it (Q39): the cook's only way to judge a mismatch without opening the
              audit view. Shown whatever state the row is in, matched or not. */}
          <p className="mt-1 font-mono text-xs text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
            {item.price != null ? `${item.name} · ${item.price.toFixed(2)}` : item.name}
          </p>
        </div>
      </div>

      {item.line_id && (
        <div className="mt-3">
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={reanalysing}
            onClick={() => setReanalysing((open) => !open)}
          >
            Re-analyse
          </Button>
          {reanalysing && (
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <div className="min-w-48 flex-1">
                <label htmlFor={`${rowId}-hint`} className={`${fieldLabelClass} sr-only`}>
                  What is it?
                </label>
                <input
                  id={`${rowId}-hint`}
                  type="text"
                  placeholder="What is it? e.g. cashew nuts"
                  value={hint}
                  disabled={reanalyse.isPending}
                  onChange={(event) => setHint(event.target.value)}
                  className={fieldInputClass}
                />
              </div>
              <Button
                size="sm"
                loading={reanalyse.isPending}
                disabled={reanalyse.isPending}
                onClick={askAgain}
              >
                Ask again
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-end gap-3">
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
