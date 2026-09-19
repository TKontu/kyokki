'use client'

/**
 * Receipts list (MVP-R8)
 * Somewhere to come back to. A receipt read by the worker is not stock until someone confirms
 * it, and the home banner only ever points at one, so this is how the rest are found again.
 */

import React from 'react'
import Link from 'next/link'
import { ReceiptStatusChip } from '@/components/receipts'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { useReceiptList } from '@/hooks/useReceipts'
import { readMethod, receiptDate, storeName } from '@/lib/receipts'
import type { ReceiptSummary } from '@/types/receipt'

/** Enough history to find anything; the pantry does not need last year's receipts. */
const PAGE_SIZE = 50

function itemSummary(receipt: ReceiptSummary): string {
  if (receipt.processing_status === 'failed') return receipt.error ?? 'No items read'
  if (!receipt.items_extracted) return 'No items read yet'
  const items = `${receipt.items_extracted} ${receipt.items_extracted === 1 ? 'item' : 'items'}`
  return `${items}, ${receipt.items_matched} already known`
}

/**
 * How the receipt was read belongs here, not only on the review screen (Q9): you cannot tell
 * which of five receipts was read badly without opening each one. A read without the model
 * is worth noticing, so it is coloured like the warning it is; a good read is a quiet aside.
 */
function ReadMethodNote({ receipt }: { receipt: ReceiptSummary }) {
  const method = receipt.processing_status === 'failed' ? null : readMethod(receipt)
  if (!method) return null

  return (
    <span
      className={
        'block truncate text-sm ' +
        (method.ok
          ? 'text-ui-text-tertiary dark:text-ui-dark-text-tertiary'
          : 'text-yellow-700 dark:text-yellow-400')
      }
    >
      {method.label}
    </span>
  )
}

function ReceiptRow({ receipt }: { receipt: ReceiptSummary }) {
  return (
    <li>
      <Link
        href={`/receipt/${receipt.id}`}
        className={
          'flex min-h-touch-lg items-center justify-between gap-3 rounded-ui border ' +
          'border-ui-border px-4 py-3 dark:border-ui-dark-border ' +
          'hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary'
        }
      >
        <span className="min-w-0">
          <span className="block truncate text-base text-ui-text dark:text-ui-dark-text">
            {`${storeName(receipt)}, ${receiptDate(receipt)}`}
          </span>
          <span className="block truncate text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {itemSummary(receipt)}
          </span>
          <ReadMethodNote receipt={receipt} />
        </span>
        <ReceiptStatusChip status={receipt.processing_status} />
      </Link>
    </li>
  )
}

export default function ReceiptsPage() {
  const { data: receipts, isLoading, isError } = useReceiptList({ limit: PAGE_SIZE })

  return (
    <div>
      <header className="flex items-center justify-between border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Receipts</h1>
        <Link
          href="/scan"
          className="text-sm text-ui-text-tertiary hover:underline dark:text-ui-dark-text-tertiary"
        >
          Scan a receipt
        </Link>
      </header>
      <main className="px-6 py-4">
        {isLoading && <SkeletonCard lines={3} />}

        {isError && (
          <p className="text-base text-ui-text-secondary dark:text-ui-dark-text-secondary">
            Could not load receipts.
          </p>
        )}

        {receipts && receipts.length === 0 && (
          <p className="text-base text-ui-text-secondary dark:text-ui-dark-text-secondary">
            No receipts yet. Share one to the Telegram bot, or{' '}
            <Link href="/scan" className="underline">
              scan one here
            </Link>
            .
          </p>
        )}

        {receipts && receipts.length > 0 && (
          <ul className="flex flex-col gap-2">
            {receipts.map((receipt) => (
              <ReceiptRow key={receipt.id} receipt={receipt} />
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
