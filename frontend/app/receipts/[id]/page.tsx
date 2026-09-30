'use client'

/**
 * Receipt audit view (Q28)
 * Reachable for every receipt, confirmed or not: the original file, the OCR text, the model's
 * raw answer and each printed line's outcome. Nothing here writes anything - it is how the
 * cook checks what the model made of a receipt, and where "fish soup" traces back to.
 */

import React, { useState } from 'react'
import Link from 'next/link'
import Badge from '@/components/ui/Badge'
import { ReceiptStatusChip } from '@/components/receipts'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { useReceiptAudit } from '@/hooks/useReceipts'
import receiptsAPI from '@/lib/api/receipts'
import { receiptDate, storeName } from '@/lib/receipts'
import type { ReceiptAudit, ReceiptAuditLine } from '@/types/receipt'

function OutcomeBadge({ outcome }: { outcome: ReceiptAuditLine['outcome'] }) {
  switch (outcome) {
    case 'stocked':
      return <Badge variant="success">Stocked</Badge>
    case 'household':
      return <Badge variant="default">Household</Badge>
    case 'skipped':
      return <Badge variant="warning">Skipped</Badge>
    default:
      return <Badge variant="info">Pending</Badge>
  }
}

/**
 * The original file (Q28): an image renders inline; a PDF goes in an `<object>` with a
 * fallback "Open" link, since not every browser embeds a PDF the same way. Neither type is
 * known until the audit response says so (the file's own bytes are never parsed here).
 */
function OriginalFile({ receiptId, contentType }: { receiptId: string; contentType: string | null }) {
  const url = receiptsAPI.fileUrl(receiptId)
  if (!contentType) {
    return (
      <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
        The original file is no longer available.
      </p>
    )
  }
  if (contentType === 'application/pdf') {
    return (
      <div className="flex flex-col gap-2">
        <object data={url} type="application/pdf" className="h-96 w-full rounded-ui border border-ui-border dark:border-ui-dark-border">
          <p className="p-3 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            This browser cannot show the PDF inline.
          </p>
        </object>
        <a href={url} target="_blank" rel="noreferrer" className="text-sm text-ui-text-tertiary underline dark:text-ui-dark-text-tertiary">
          Open the original
        </a>
      </div>
    )
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt="The scanned receipt"
      className="max-h-96 w-full rounded-ui border border-ui-border object-contain dark:border-ui-dark-border"
    />
  )
}

/** A stocked line's items, each linking to the product it became (no per-item page exists). */
function StockedItems({ items }: { items: ReceiptAuditLine['items'] }) {
  if (items.length === 0) return null
  return (
    <ul className="mt-1 flex flex-wrap gap-2">
      {items.map((item) => (
        <li key={item.id}>
          <Link href="/products" className="text-sm text-ui-text-tertiary underline dark:text-ui-dark-text-tertiary">
            {item.product_name ?? 'a product'}
          </Link>
        </li>
      ))}
    </ul>
  )
}

function LineRow({ line }: { line: ReceiptAuditLine }) {
  return (
    <li className="rounded-ui border border-ui-border p-3 dark:border-ui-dark-border">
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0 flex-1 break-words text-base text-ui-text dark:text-ui-dark-text">
          {line.name}
        </span>
        <OutcomeBadge outcome={line.outcome} />
      </div>
      {line.price !== null && (
        <span className="text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
          {line.price.toFixed(2)}
        </span>
      )}
      <StockedItems items={line.items} />
    </li>
  )
}

/** Items created before the line index existed (no backfill, Q26): shown, not attributed. */
function UnlinkedItems({ items }: { items: ReceiptAudit['unlinked_items'] }) {
  if (items.length === 0) return null
  return (
    <section className="mt-4">
      <h2 className="text-base font-medium text-ui-text dark:text-ui-dark-text">
        Also created from this receipt (line unknown)
      </h2>
      <ul className="mt-2 flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id} className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            <Link href="/products" className="underline">
              {item.product_name ?? 'a product'}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

/**
 * Collapsible, monospace and scrollable; rendered as plain text, never parsed as HTML
 * (spec). Mirrors the review screen's own "Show receipt text" toggle (Q27/Q28).
 */
function TextBlock({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false)
  const region = `audit-text-${label.replace(/\s+/g, '-').toLowerCase()}`
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={region}
        onClick={() => setOpen((shown) => !shown)}
        className="min-h-touch text-sm text-ui-text-secondary underline dark:text-ui-dark-text-secondary"
      >
        {open ? `Hide ${label}` : `Show ${label}`}
      </button>
      <pre
        id={region}
        hidden={!open}
        className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-ui border border-ui-border bg-gray-50 p-3 font-mono text-xs text-ui-text dark:border-ui-dark-border dark:bg-gray-900 dark:text-ui-dark-text"
      >
        {text}
      </pre>
    </div>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <header className="flex items-center justify-between border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Receipt audit</h1>
        <Link
          href="/receipts"
          className="text-sm text-ui-text-tertiary hover:underline dark:text-ui-dark-text-tertiary"
        >
          Back to receipts
        </Link>
      </header>
      <main className="px-6 py-4">{children}</main>
    </div>
  )
}

export default function ReceiptAuditPage({ params }: { params: { id: string } }) {
  const { data: audit, isLoading, isError } = useReceiptAudit(params.id)

  if (isLoading) {
    return (
      <Frame>
        <SkeletonCard lines={4} />
      </Frame>
    )
  }

  if (isError || !audit) {
    return (
      <Frame>
        <p role="alert" className="text-ui-text dark:text-ui-dark-text">
          Receipt not found.
        </p>
      </Frame>
    )
  }

  return (
    <Frame>
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <span className="min-w-0">
            <span className="block truncate text-lg text-ui-text dark:text-ui-dark-text">
              {`${storeName(audit)}, ${receiptDate(audit)}`}
            </span>
          </span>
          <ReceiptStatusChip status={audit.processing_status} />
        </div>

        <OriginalFile receiptId={audit.id} contentType={audit.file_content_type} />

        <section>
          <h2 className="text-base font-medium text-ui-text dark:text-ui-dark-text">Lines</h2>
          {audit.lines.length === 0 ? (
            <p className="mt-2 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
              No lines were read from this receipt.
            </p>
          ) : (
            <ul className="mt-2 flex flex-col gap-2">
              {audit.lines.map((line) => (
                <LineRow key={line.index} line={line} />
              ))}
            </ul>
          )}
          <UnlinkedItems items={audit.unlinked_items} />
        </section>

        <div className="flex flex-col gap-2">
          {audit.ocr_raw_text && <TextBlock label="OCR text" text={audit.ocr_raw_text} />}
          {audit.model_raw_answer && (
            <TextBlock label="Model's answer" text={audit.model_raw_answer} />
          )}
        </div>

        {audit.processing_status !== 'confirmed' && (
          <Link
            href={`/receipt/${audit.id}`}
            className="text-sm text-ui-text-tertiary underline dark:text-ui-dark-text-tertiary"
          >
            Go to the review screen
          </Link>
        )}
      </div>
    </Frame>
  )
}
