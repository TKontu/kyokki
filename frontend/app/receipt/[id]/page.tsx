'use client'

/**
 * Receipt review page (MVP-R7)
 * The last step of the receipt path: a receipt read by the worker becomes stock here. Lines
 * arrive with a generic name, amount and category suggestion; the cook fixes what is wrong,
 * skips what should not be stocked, and confirms.
 */

import React, { useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import Button from '@/components/ui/Button'
import { ReceiptItemRow, canInclude, type ReviewRow } from '@/components/receipts/ReceiptItemRow'
import { useCategories } from '@/hooks/useCategories'
import { useConfirmReceipt, useReceipt, useReprocessReceipt } from '@/hooks/useReceipts'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { toISODate } from '@/lib/dates'
import { receiptDate, storeName } from '@/lib/receipts'
import type { ConfirmedItemCreate, ExtractedItem } from '@/types/receipt'

function initialRow(item: ExtractedItem): ReviewRow {
  const name = item.generic_name ?? item.name
  const category = item.suggested_category ?? ''
  return {
    index: item.index,
    // A line with nothing to go on starts skipped rather than silently creating a product
    include: Boolean(item.product_id) || (name.trim() !== '' && category !== ''),
    name,
    category,
    quantity: String(item.quantity),
    unit: item.unit,
  }
}

const mainClass = 'px-6 py-4'

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <header className="flex items-center justify-between border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Receipt</h1>
        <Link
          href="/receipts"
          className="text-sm text-ui-text-tertiary hover:underline dark:text-ui-dark-text-tertiary"
        >
          Back to receipts
        </Link>
      </header>
      <main className={mainClass}>{children}</main>
    </div>
  )
}

export default function ReceiptReviewPage({ params }: { params: { id: string } }) {
  const router = useRouter()
  const toast = useToast()
  const { data: receipt, isLoading, isError } = useReceipt(params.id)
  const { data: categories } = useCategories()
  const confirm = useConfirmReceipt()
  const reprocess = useReprocessReceipt()

  // Edits live here, keyed by line index; a row not touched yet uses the read values.
  const [edits, setEdits] = useState<Record<number, Partial<ReviewRow>>>({})

  const sortedCategories = useMemo(
    () => [...(categories ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [categories]
  )

  const rows: { item: ExtractedItem; row: ReviewRow }[] = useMemo(() => {
    if (!receipt) return []
    return receipt.items.map((item) => {
      const base = initialRow(item)
      const change = edits[item.index] ?? {}
      const row = { ...base, ...change }
      // Choosing a category (or naming the line) includes it unless it was skipped on purpose
      if (change.include === undefined && !base.include && canInclude(item, row)) {
        row.include = true
      }
      return { item, row }
    })
  }, [receipt, edits])

  if (isLoading) {
    return (
      <Frame>
        <div className="h-24 animate-pulse rounded-ui bg-gray-200 dark:bg-gray-700" aria-label="Loading receipt" />
      </Frame>
    )
  }

  if (isError || !receipt) {
    return (
      <Frame>
        <p role="alert" className="text-ui-text dark:text-ui-dark-text">
          Receipt not found.
        </p>
      </Frame>
    )
  }

  const status = receipt.processing_status

  if (status === 'queued' || status === 'processing') {
    return (
      <Frame>
        <p className="text-ui-text dark:text-ui-dark-text">
          Still reading this receipt… it usually takes about a minute.
        </p>
      </Frame>
    )
  }

  if (status === 'failed') {
    return (
      <Frame>
        <p role="alert" className="mb-4 text-ui-text dark:text-ui-dark-text">
          This receipt could not be read.
        </p>
        {receipt.error && (
          <p className="mb-4 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {receipt.error}
          </p>
        )}
        <Button
          size="lg"
          loading={reprocess.isPending}
          onClick={() =>
            reprocess.mutate(receipt.id, {
              onError: () => toast.error('Could not queue this receipt'),
            })
          }
        >
          Read again
        </Button>
      </Frame>
    )
  }

  if (status === 'confirmed') {
    return (
      <Frame>
        <p className="text-ui-text dark:text-ui-dark-text">
          {`${storeName(receipt)}, ${receiptDate(receipt)}: already added to your stock.`}
        </p>
      </Frame>
    )
  }

  const included = rows.filter(({ row }) => row.include)
  const skipped = rows.length - included.length
  const purchaseDate = receipt.purchase_date ?? toISODate(new Date())

  const submit = () => {
    const items: ConfirmedItemCreate[] = included.map(({ item, row }) =>
      item.product_id
        ? {
            index: item.index,
            product_id: item.product_id,
            quantity: Number(row.quantity),
            unit: row.unit,
            purchase_date: purchaseDate,
          }
        : {
            index: item.index,
            name: row.name.trim(),
            category: row.category,
            quantity: Number(row.quantity),
            unit: row.unit,
            purchase_date: purchaseDate,
          }
    )

    confirm.mutate(
      { id: receipt.id, data: { items } },
      {
        onSuccess: (result) => {
          const noun = result.items_created === 1 ? 'item' : 'items'
          toast.success(`Added ${result.items_created} ${noun} · ${storeName(receipt)}`)
          router.push('/')
        },
        // Keep the review open so nothing edited is lost; 4xx messages are meant for people.
        onError: (error) => {
          const clientError = isAPIError(error) && error.status < 500 && error.message
          toast.error(clientError ? error.message : 'Could not add these items')
        },
      }
    )
  }

  const quantitiesValid = included.every(({ row }) => Number(row.quantity) > 0)

  return (
    <div>
      <header className="border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">
            {`${storeName(receipt)}, ${receiptDate(receipt)}`}
          </h1>
          <Link
            href="/receipts"
            className="text-sm text-ui-text-tertiary hover:underline dark:text-ui-dark-text-tertiary"
          >
            Back to receipts
          </Link>
        </div>
        <p className="mt-1 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {`${receipt.items.length} items read, ${receipt.items_matched} already known`}
        </p>
        {receipt.extraction_method === 'heuristic' && (
          <p className="mt-2 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            Read without the AI model, so names are as printed.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => reprocess.mutate(receipt.id)}
            >
              Read again with the model
            </button>
          </p>
        )}
      </header>

      <main className={`${mainClass} pb-32`}>
        <ul className="flex flex-col gap-3">
          {rows.map(({ item, row }) => (
            <li key={item.index}>
              <ReceiptItemRow
                item={item}
                row={row}
                categories={sortedCategories}
                onChange={(changes) =>
                  setEdits((current) => ({
                    ...current,
                    [item.index]: { ...current[item.index], ...changes },
                  }))
                }
              />
            </li>
          ))}
        </ul>
      </main>

      <footer className="fixed inset-x-0 bottom-0 flex items-center justify-between gap-4 border-t border-ui-border bg-white px-6 py-3 pb-[env(safe-area-inset-bottom)] dark:border-ui-dark-border dark:bg-ui-dark-bg">
        <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {skipped > 0 ? `${skipped} skipped` : 'Nothing skipped'}
        </p>
        <Button
          size="lg"
          disabled={included.length === 0 || !quantitiesValid || confirm.isPending}
          loading={confirm.isPending}
          onClick={submit}
        >
          {`Add ${included.length} ${included.length === 1 ? 'item' : 'items'}`}
        </Button>
      </footer>
    </div>
  )
}
