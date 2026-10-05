'use client'

/**
 * Scan page (MVP-R6)
 * The iPad's way in. Most receipts arrive through the Telegram bot; this is for the paper ones
 * on the counter and for a phone that is not to hand. Uploading queues the receipt, so the page
 * hands straight over to the review screen, which already shows the reading state.
 *
 * Several files can be picked at once (Post-MVP frontier item 8). Each becomes its own receipt,
 * uploaded one at a time (the OCR worker reads one file at a time anyway), and a failed file
 * does not stop the rest. One file still goes straight to its receipt, several go to the
 * receipt list, and any failure keeps the page with what happened to each file.
 */

import React, { Suspense, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import Button from '@/components/ui/Button'
import { fieldHintClass, fieldInputClass, fieldLabelClass } from '@/components/ui/formStyles'
import { useUploadReceipt } from '@/hooks/useReceipts'
import { useT } from '@/lib/i18n'
import { isAPIError } from '@/lib/api/errors'
import { downscaleImage } from '@/lib/images'

const ACCEPT = 'image/*,application/pdf'

const linkClass = 'min-h-touch text-base text-ui-text underline dark:text-ui-dark-text'

/** A second upload of the same file is refused, and the answer says which receipt it was. */
function existingReceiptId(error: unknown): string | null {
  if (!isAPIError(error) || error.status !== 409) return null
  const { receipt_id: id } = (error.details ?? {}) as { receipt_id?: unknown }
  return typeof id === 'string' ? id : null
}

/** What became of one picked file. */
type Outcome =
  | { name: string; kind: 'uploaded' | 'existing'; id: string }
  | { name: string; kind: 'failed'; message: string }

export default function ScanPage() {
  // `useSearchParams` (the share target's `?shared=failed`) opts the page out of static
  // rendering unless it sits under its own Suspense boundary - Next.js's requirement, not a
  // loading state the page ever shows.
  return (
    <Suspense fallback={null}>
      <ScanPageContent />
    </Suspense>
  )
}

function ScanPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useT()
  const upload = useUploadReceipt()
  const [files, setFiles] = useState<File[]>([])
  const [storeChain, setStoreChain] = useState('')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null)
  const [results, setResults] = useState<Outcome[] | null>(null)
  const [picked, setPicked] = useState(false)

  // The share target sends the cook here when none of the shared files could be queued
  const shareFailed = searchParams?.get('shared') === 'failed' && !picked
  const running = progress !== null

  const uploadOne = async (file: File): Promise<Outcome> => {
    try {
      // A 12 MP capture costs OCR time without reading any better
      const toSend = await downscaleImage(file)
      const receipt = await upload.mutateAsync({
        file: toSend,
        fields: { store_chain: storeChain.trim(), purchase_date: purchaseDate },
      })
      return { name: file.name, kind: 'uploaded', id: receipt.id }
    } catch (error) {
      const existing = existingReceiptId(error)
      // Nothing went wrong, the receipt is simply already here
      if (existing) return { name: file.name, kind: 'existing', id: existing }
      return {
        name: file.name,
        kind: 'failed',
        message: isAPIError(error) ? error.message : t('scan.uploadError'),
      }
    }
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (files.length === 0 || running) return
    setMessage(null)
    setResults(null)

    // One request at a time, in the order picked: the worker reads one file at a time
    const outcomes: Outcome[] = []
    for (let index = 0; index < files.length; index++) {
      setProgress({ current: index + 1, total: files.length })
      outcomes.push(await uploadOne(files[index]))
    }
    setProgress(null)

    const failures = outcomes.filter((outcome) => outcome.kind === 'failed')
    if (failures.length === 0) {
      const only = outcomes.length === 1 ? outcomes[0] : null
      router.push(only && only.kind !== 'failed' ? `/receipt/${only.id}` : '/receipts')
      return
    }
    const only = outcomes.length === 1 ? outcomes[0] : null
    if (only?.kind === 'failed') setMessage(only.message)
    else setResults(outcomes)
  }

  const outcomeText = (outcome: Outcome) => {
    if (outcome.kind === 'failed') return t('scan.resultFailed', { message: outcome.message })
    return t(outcome.kind === 'uploaded' ? 'scan.resultUploaded' : 'scan.resultExisting')
  }

  return (
    <div>
      <header className="border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">
          {t('scan.title')}
        </h1>
      </header>
      <main className="px-6 py-4">
        {shareFailed && (
          <p
            role="status"
            className={
              'mb-4 max-w-xl rounded-ui border border-amber-300 bg-amber-50 px-4 py-3 text-base ' +
              'text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200'
            }
          >
            {t('scan.sharedFailed')}
          </p>
        )}
        <form className="flex max-w-xl flex-col gap-4" onSubmit={submit}>
          <div>
            <label className={fieldLabelClass} htmlFor="receipt-file">
              {t('scan.fileLabel')}
            </label>
            <input
              id="receipt-file"
              type="file"
              accept={ACCEPT}
              multiple
              className={`${fieldInputClass} py-2`}
              onChange={(event) => {
                setFiles(Array.from(event.target.files ?? []))
                setPicked(true)
                setMessage(null)
                setResults(null)
              }}
            />
            <p className={fieldHintClass}>{t('scan.fileHint')}</p>
            {files.length > 1 && <p className={fieldHintClass}>{t('scan.manyHint')}</p>}
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="receipt-store">
              {t('scan.storeLabel')}
            </label>
            <input
              id="receipt-store"
              type="text"
              value={storeChain}
              placeholder={t('scan.storePlaceholder')}
              className={fieldInputClass}
              onChange={(event) => setStoreChain(event.target.value)}
            />
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="receipt-date">
              {t('scan.dateLabel')}
            </label>
            <input
              id="receipt-date"
              type="date"
              value={purchaseDate}
              className={fieldInputClass}
              onChange={(event) => setPurchaseDate(event.target.value)}
            />
          </div>

          {message && (
            <p role="alert" className="text-base text-red-700 dark:text-red-400">
              {message}
            </p>
          )}

          {progress && (
            <p className="text-base text-ui-text dark:text-ui-dark-text">
              {t('scan.progress', progress)}
            </p>
          )}

          <Button type="submit" size="lg" disabled={files.length === 0} loading={running}>
            {files.length > 1 ? t('scan.uploadMany', { count: files.length }) : t('scan.upload')}
          </Button>
        </form>

        {results && (
          <section className="mt-6 max-w-xl">
            <h2
              id="scan-results"
              className="mb-2 text-lg font-semibold text-ui-text dark:text-ui-dark-text"
            >
              {t('scan.results')}
            </h2>
            <ul aria-labelledby="scan-results" className="flex flex-col gap-2">
              {results.map((outcome, index) => (
                <li
                  key={`${index}-${outcome.name}`}
                  className="flex flex-wrap items-baseline justify-between gap-2 text-base"
                >
                  <span className="break-all text-ui-text dark:text-ui-dark-text">
                    {outcome.name}
                  </span>
                  {outcome.kind === 'failed' ? (
                    <span className="text-red-700 dark:text-red-400">{outcomeText(outcome)}</span>
                  ) : (
                    <Link href={`/receipt/${outcome.id}`} className={linkClass}>
                      {outcomeText(outcome)}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
            <Link href="/receipts" className={`${linkClass} mt-4 inline-block`}>
              {t('scan.allReceipts')}
            </Link>
          </section>
        )}
      </main>
    </div>
  )
}
