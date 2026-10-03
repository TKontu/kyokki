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
import { useT } from '@/lib/i18n'
import { readMethod, receiptDate, storeName } from '@/lib/receipts'
import type { Language } from '@/lib/language'
import type { ReceiptSummary } from '@/types/receipt'

/** Enough history to find anything; the pantry does not need last year's receipts. */
const PAGE_SIZE = 50

function itemSummary(
  receipt: ReceiptSummary,
  t: (key: string, params?: Record<string, string | number>) => string
): string {
  if (receipt.processing_status === 'failed')
    return receipt.error ?? t('receipts.list.noItemsRead')
  if (!receipt.items_extracted) return t('receipts.list.noItemsYet')
  return t('receipts.list.itemSummary', {
    count: receipt.items_extracted,
    matched: receipt.items_matched,
  })
}

/**
 * How the receipt was read belongs here, not only on the review screen (Q9): you cannot tell
 * which of five receipts was read badly without opening each one. A read without the model
 * is worth noticing, so it is coloured like the warning it is; a good read is a quiet aside.
 */
function ReadMethodNote({ receipt, language }: { receipt: ReceiptSummary; language: Language }) {
  const method = receipt.processing_status === 'failed' ? null : readMethod(receipt, language)
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

/**
 * A confirmed receipt has nothing left to review, so it opens the audit view (Q28) instead
 * of the review screen; everything else keeps going through the review flow as before.
 */
function receiptHref(receipt: Pick<ReceiptSummary, 'id' | 'processing_status'>): string {
  return receipt.processing_status === 'confirmed'
    ? `/receipts/${receipt.id}`
    : `/receipt/${receipt.id}`
}

function ReceiptRow({
  receipt,
  t,
  language,
}: {
  receipt: ReceiptSummary
  t: (key: string, params?: Record<string, string | number>) => string
  language: Language
}) {
  return (
    <li>
      <Link
        href={receiptHref(receipt)}
        className={
          'flex min-h-touch-lg items-center justify-between gap-3 rounded-ui border ' +
          'border-ui-border px-4 py-3 dark:border-ui-dark-border ' +
          'hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary'
        }
      >
        <span className="min-w-0">
          <span className="block truncate text-base text-ui-text dark:text-ui-dark-text">
            {`${storeName(receipt, language)}, ${receiptDate(receipt, language)}`}
          </span>
          <span className="block truncate text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {itemSummary(receipt, t)}
          </span>
          <ReadMethodNote receipt={receipt} language={language} />
        </span>
        <ReceiptStatusChip status={receipt.processing_status} />
      </Link>
    </li>
  )
}

export default function ReceiptsPage() {
  const { t, language } = useT()
  const { data: receipts, isLoading, isError } = useReceiptList({ limit: PAGE_SIZE })

  return (
    <div>
      <header className="flex items-center justify-between border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">
          {t('receipts.list.title')}
        </h1>
        <Link
          href="/scan"
          className="text-sm text-ui-text-tertiary hover:underline dark:text-ui-dark-text-tertiary"
        >
          {t('receipts.list.scanLink')}
        </Link>
      </header>
      <main className="px-6 py-4">
        {isLoading && <SkeletonCard lines={3} />}

        {isError && (
          <p className="text-base text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {t('receipts.list.loadError')}
          </p>
        )}

        {receipts && receipts.length === 0 && (
          <p className="text-base text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {t('receipts.list.emptyPrefix')}{' '}
            <Link href="/scan" className="underline">
              {t('receipts.list.emptyScanLink')}
            </Link>
            .
          </p>
        )}

        {receipts && receipts.length > 0 && (
          <ul className="flex flex-col gap-2">
            {receipts.map((receipt) => (
              <ReceiptRow key={receipt.id} receipt={receipt} t={t} language={language} />
            ))}
          </ul>
        )}
      </main>
    </div>
  )
}
