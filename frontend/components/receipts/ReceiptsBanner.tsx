'use client'

/**
 * ReceiptsBanner
 * Above the stock list: what a receipt drop-off is waiting for. Receipts arrive through the
 * Telegram bot, are read by the worker, and then need a review before they become stock.
 */

import React from 'react'
import Link from 'next/link'
import { isBeingRead, useReceiptList } from '@/hooks/useReceipts'
import type { Receipt } from '@/types/receipt'

const boxClass =
  'mb-4 flex min-h-touch items-center gap-2 rounded-ui border px-4 py-3 text-base ' +
  'border-ui-border dark:border-ui-dark-border bg-ui-bg-secondary dark:bg-ui-dark-bg-secondary ' +
  'text-ui-text dark:text-ui-dark-text'

function newest(receipts: Receipt[]): Receipt {
  return [...receipts].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
}

export function ReceiptsBanner() {
  const { data: receipts } = useReceiptList()
  if (!receipts?.length) return null

  const waiting = receipts.filter((receipt) => receipt.processing_status === 'completed')
  const reading = receipts.filter(isBeingRead)
  const failed = receipts.filter((receipt) => receipt.processing_status === 'failed')

  if (waiting.length) {
    const noun = waiting.length === 1 ? 'receipt' : 'receipts'
    return (
      <Link href={`/receipt/${newest(waiting).id}`} className={`${boxClass} hover:underline`}>
        <span aria-hidden="true">🧾</span>
        {`${waiting.length} ${noun} waiting to review`}
      </Link>
    )
  }

  if (reading.length) {
    return (
      <p className={boxClass}>
        <span aria-hidden="true">🧾</span>
        {reading.length === 1 ? 'Reading a receipt…' : `Reading ${reading.length} receipts…`}
      </p>
    )
  }

  if (failed.length) {
    return (
      <Link href={`/receipt/${newest(failed).id}`} className={`${boxClass} hover:underline`}>
        <span aria-hidden="true">⚠️</span>
        {failed.length === 1
          ? 'A receipt could not be read'
          : `${failed.length} receipts could not be read`}
      </Link>
    )
  }

  return null
}

export default ReceiptsBanner
