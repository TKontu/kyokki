'use client'

/**
 * ReceiptItemRow
 * One read receipt line on the review screen: include it or skip it, fix the name, amount and
 * category. A line already matched to a product keeps that product and needs no category.
 *
 * CL8 L1: a line joins a product only on an exact key. Anything weaker arrives as
 * `item.suggestion`, and the row starts as a new product with the suggestion shown beneath it:
 * the cook taps Accept to use it (the operator's ruling of 2026-10-07 - suggestions are never
 * used untouched), or Search to pick another. A confirm refused with 409 `name_exists` marks
 * the row so the cook can use the existing product or rename this one.
 */

import React, { useRef, useState } from 'react'
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
import { useT, type TranslateParams } from '@/lib/i18n'
import { storeName } from '@/lib/receipts'
import type { Category } from '@/types/category'
import type { ExtractedItem, ReceiptSuggestion, ReceiptUnit } from '@/types/receipt'

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
  /** `productId` is the line's suggestion, which the cook accepted (CL8 L1). */
  acceptedSuggestion?: boolean
  /**
   * Confirm answered 409 `name_exists` for this row's new-product name: the product that
   * already has it, for the "Use it, or rename" choice. Cleared by either.
   */
  nameExists?: { productId: string; productName: string } | null
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
  /** The receipt's chain, to say where an unverified alias was learned (CL8 L1). */
  storeChain?: string | null
}


/** The product this row will actually use: the cook's choice, else what was read. */
export function chosenProductId(item: ExtractedItem, row: ReviewRow): string | null {
  return row.productId === undefined ? item.product_id : row.productId
}

/**
 * The product proposed for this line, if any. A keyed line has none (the contract never sends
 * both); a suggestion is only ever a proposal - it is not the row's product until accepted.
 */
export function lineSuggestion(item: ExtractedItem): ReceiptSuggestion | null {
  return item.product_id ? null : (item.suggestion ?? null)
}

/** The row uses its suggestion because the cook accepted it (Accept or Accept all). */
export function suggestionAccepted(item: ExtractedItem, row: ReviewRow): boolean {
  const suggestion = lineSuggestion(item)
  return Boolean(
    suggestion && row.acceptedSuggestion && row.productId === suggestion.product_id
  )
}

/** What accepting a line's suggestion changes on its row. */
export function acceptChanges(suggestion: ReceiptSuggestion): Partial<ReviewRow> {
  return {
    productId: suggestion.product_id,
    productName: suggestion.product_name,
    acceptedSuggestion: true,
    nameExists: null,
  }
}

/** Why a product was suggested, in plain words. */
function reasonText(
  suggestion: ReceiptSuggestion,
  storeChain: string | null | undefined,
  t: (key: string, params?: TranslateParams) => string,
  language: Parameters<typeof storeName>[1]
): string {
  const chain = (value: string | null | undefined) =>
    storeName({ store_chain: value ?? null }, language)
  switch (suggestion.reason) {
    case 'selected':
      return t('receipt.itemRow.reason.selected')
    case 'unverified_alias':
      return t('receipt.itemRow.reason.unverifiedAlias', { chain: chain(storeChain) })
    case 'other_chain_alias':
      return suggestion.store_chain
        ? t('receipt.itemRow.reason.otherChainAliasAt', { chain: chain(suggestion.store_chain) })
        : t('receipt.itemRow.reason.otherChainAlias')
    case 'model_name':
      return t('receipt.itemRow.reason.modelName')
    case 'generic_name':
      return t('receipt.itemRow.reason.genericName')
    default:
      return ''
  }
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
  storeChain,
}: ReceiptItemRowProps) {
  const [changing, setChanging] = useState(false)
  const [searchTerm, setSearchTerm] = useState(row.name)
  const [reanalysing, setReanalysing] = useState(false)
  const [hint, setHint] = useState('')
  const toast = useToast()
  const reanalyse = useReanalyseLine()
  const { t, language } = useT()
  // Read at response time, not at click time (F3): a mutation can take a while, and an
  // edit made to this row while it is in flight must still be caught. A plain closure
  // over the `dirty` prop would answer with whatever it was when `askAgain` was called.
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty
  const productId = chosenProductId(item, row)
  const matched = Boolean(productId)
  const ready = canInclude(item, row)
  const rowId = `row-${item.index}`
  const productName =
    row.productName !== undefined ? row.productName : item.product_name
  // The cook's own choice is their word, whatever the read proposed.
  const chosenByCook = row.productId !== undefined
  const suggestion = lineSuggestion(item)
  const accepted = suggestionAccepted(item, row)
  const clash = !matched && row.nameExists ? row.nameExists : null

  const askAgain = () => {
    if (!item.line_id) return
    reanalyse.mutate(
      { receiptId, lineId: item.line_id, hint: hint.trim() || null },
      {
        onSuccess: (updated) => {
          if (dirtyRef.current && !window.confirm(t('receipt.itemRow.confirmOverwrite'))) {
            return
          }
          onReanalysed(updated)
          setReanalysing(false)
          setHint('')
        },
        onError: (error) => {
          toast.error(
            isAPIError(error) ? error.message : t('receipt.itemRow.reanalyseError')
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
          aria-label={t('receipt.itemRow.include', { name: row.name || item.name })}
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
                aria-label={t('receipt.itemRow.changeAriaLabel', { name: productName ?? item.name })}
              >
                {t('receipt.itemRow.change')}
              </Button>
              {accepted && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    // Back to new: the line is a new product named by `name` again
                    onChange({ productId: null, productName: null, acceptedSuggestion: false })
                  }
                  aria-label={t('receipt.itemRow.undoAcceptAriaLabel', {
                    name: productName ?? item.name,
                  })}
                >
                  {t('receipt.itemRow.undoAccept')}
                </Button>
              )}
            </div>
          ) : (
            <>
              {suggestion && (
                <p className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                  {t('receipt.itemRow.newRow', { name: row.name })}
                </p>
              )}
              <label htmlFor={`${rowId}-name`} className={`${fieldLabelClass} sr-only`}>
                {t('receipt.itemRow.productNameLabel')}
              </label>
              <input
                id={`${rowId}-name`}
                type="text"
                aria-label={t('receipt.itemRow.productNameLabel')}
                value={row.name}
                onChange={(event) => onChange({ name: event.target.value, nameExists: null })}
                className={fieldInputClass}
              />
              {clash && (
                <p
                  role="alert"
                  className="mt-1 flex flex-wrap items-center gap-2 text-sm text-yellow-700 dark:text-yellow-400"
                >
                  <span>{t('receipt.itemRow.nameExists', { name: row.name })}</span>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      // The cook's pick, not an accepted suggestion
                      onChange({
                        productId: clash.productId,
                        productName: clash.productName,
                        acceptedSuggestion: false,
                        nameExists: null,
                      })
                    }
                  >
                    {t('receipt.itemRow.useProduct', { name: clash.productName })}
                  </Button>
                  <span>{t('receipt.itemRow.orRename')}</span>
                </p>
              )}
              {suggestion && !changing && (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-ui border border-dashed border-ui-border p-2 dark:border-ui-dark-border">
                  <p className="text-sm text-ui-text dark:text-ui-dark-text">
                    {t('receipt.itemRow.suggested', { name: suggestion.product_name })}
                  </p>
                  <span className="text-xs text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
                    {reasonText(suggestion, storeChain, t, language)}
                  </span>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onChange(acceptChanges(suggestion))}
                    aria-label={t('receipt.itemRow.acceptAriaLabel', {
                      name: suggestion.product_name,
                    })}
                  >
                    {t('receipt.itemRow.accept')}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setChanging(true)}
                    aria-label={t('receipt.itemRow.searchAriaLabel', { name: item.name })}
                  >
                    {t('receipt.itemRow.search')}
                  </Button>
                </div>
              )}
              {!suggestion && !changing && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-1"
                  onClick={() => setChanging(true)}
                  aria-label={t('receipt.itemRow.findExistingAriaLabel', { name: item.name })}
                >
                  {t('receipt.itemRow.findExisting')}
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
                newLabel={(term) => t('receipt.itemRow.newProduct', { term })}
                onPickExisting={(product) => {
                  onChange({
                    productId: product.id,
                    productName: product.canonical_name,
                    name: product.canonical_name,
                    acceptedSuggestion: false,
                    nameExists: null,
                  })
                  setChanging(false)
                }}
                onPickNew={(name) => {
                  // Detach: the line becomes a new product named here, and confirm
                  // learns the printed name against it (H15).
                  onChange({
                    productId: null,
                    productName: null,
                    name,
                    acceptedSuggestion: false,
                    nameExists: null,
                  })
                  setChanging(false)
                }}
              />
              <Button
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => setChanging(false)}
              >
                {t('common.cancel')}
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
            {t('receipt.itemRow.reanalyse')}
          </Button>
          {reanalysing && (
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <div className="min-w-48 flex-1">
                <label htmlFor={`${rowId}-hint`} className={`${fieldLabelClass} sr-only`}>
                  {t('receipt.itemRow.whatIsIt')}
                </label>
                <input
                  id={`${rowId}-hint`}
                  type="text"
                  placeholder={t('receipt.itemRow.whatIsItPlaceholder')}
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
                {t('receipt.itemRow.askAgain')}
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-end gap-3">
        {!matched && (
          <div className="min-w-48 flex-1">
            <label htmlFor={`${rowId}-category`} className={fieldLabelClass}>
              {t('common.category')}
            </label>
            <select
              id={`${rowId}-category`}
              aria-label={t('common.category')}
              value={row.category}
              onChange={(event) => onChange({ category: event.target.value })}
              className={`${fieldInputClass} mt-1`}
            >
              <option value="">{t('receipt.pickCategory')}</option>
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
            ? t('receipt.itemRow.needName')
            : t('receipt.itemRow.needCategory')}
        </p>
      )}
    </div>
  )
}

export default ReceiptItemRow
