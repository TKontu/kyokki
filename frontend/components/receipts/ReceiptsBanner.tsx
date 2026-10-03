'use client'

/**
 * ReceiptsBanner
 * Above the stock list: what a receipt drop-off is waiting for. Receipts arrive through the
 * Telegram bot, are read by the worker, and then need a review before they become stock.
 */

import React from 'react'
import Link from 'next/link'
import { isBeingRead, useReceiptList } from '@/hooks/useReceipts'
import { useT } from '@/lib/i18n'
import type { ReceiptSummary } from '@/types/receipt'

const boxClass =
  'mb-4 flex min-h-touch items-center gap-2 rounded-ui border px-4 py-3 text-base ' +
  'border-ui-border dark:border-ui-dark-border bg-ui-bg-secondary dark:bg-ui-dark-bg-secondary ' +
  'text-ui-text dark:text-ui-dark-text'

/** One receipt opens straight away; several are worth choosing between (MVP-R8). */
function destination(receipts: ReceiptSummary[]): string {
  return receipts.length === 1 ? `/receipt/${receipts[0].id}` : '/receipts'
}

export function ReceiptsBanner() {
  const { t } = useT()
  const { data: receipts } = useReceiptList()
  if (!receipts?.length) return null

  const waiting = receipts.filter((receipt) => receipt.processing_status === 'completed')
  const reading = receipts.filter(isBeingRead)
  const failed = receipts.filter((receipt) => receipt.processing_status === 'failed')

  if (waiting.length) {
    return (
      <Link href={destination(waiting)} className={`${boxClass} hover:underline`}>
        <span aria-hidden="true">🧾</span>
        {t('receipts.banner.waiting', { count: waiting.length })}
      </Link>
    )
  }

  if (reading.length) {
    return (
      <p className={boxClass}>
        <span aria-hidden="true">🧾</span>
        {t('receipts.banner.reading', { count: reading.length })}
      </p>
    )
  }

  if (failed.length) {
    return (
      <Link href={destination(failed)} className={`${boxClass} hover:underline`}>
        <span aria-hidden="true">⚠️</span>
        {t('receipts.banner.failed', { count: failed.length })}
      </Link>
    )
  }

  return null
}

export default ReceiptsBanner
