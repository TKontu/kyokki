'use client'

/**
 * Scan page (MVP-R6)
 * The iPad's way in. Most receipts arrive through the Telegram bot; this is for the paper ones
 * on the counter and for a phone that is not to hand. Uploading queues the receipt, so the page
 * hands straight over to the review screen, which already shows the reading state.
 */

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import Button from '@/components/ui/Button'
import { fieldHintClass, fieldInputClass, fieldLabelClass } from '@/components/ui/formStyles'
import { useUploadReceipt } from '@/hooks/useReceipts'
import { isAPIError } from '@/lib/api/errors'
import { downscaleImage } from '@/lib/images'

const ACCEPT = 'image/*,application/pdf'

/** A second upload of the same file is refused, and the answer says which receipt it was. */
function existingReceiptId(error: unknown): string | null {
  if (!isAPIError(error) || error.status !== 409) return null
  const { receipt_id: id } = (error.details ?? {}) as { receipt_id?: unknown }
  return typeof id === 'string' ? id : null
}

export default function ScanPage() {
  const router = useRouter()
  const upload = useUploadReceipt()
  const [file, setFile] = useState<File | null>(null)
  const [storeChain, setStoreChain] = useState('')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file || upload.isPending) return
    setMessage(null)

    try {
      // A 12 MP capture costs OCR time without reading any better
      const toSend = await downscaleImage(file)
      const receipt = await upload.mutateAsync({
        file: toSend,
        fields: { store_chain: storeChain.trim(), purchase_date: purchaseDate },
      })
      router.push(`/receipt/${receipt.id}`)
    } catch (error) {
      const existing = existingReceiptId(error)
      if (existing) {
        // Nothing went wrong, the receipt is simply already here
        router.push(`/receipt/${existing}`)
        return
      }
      setMessage(
        isAPIError(error) ? error.message : 'Could not upload the receipt. Try again.'
      )
    }
  }

  return (
    <div>
      <header className="border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">
          Scan a receipt
        </h1>
      </header>
      <main className="px-6 py-4">
        <form className="flex max-w-xl flex-col gap-4" onSubmit={submit}>
          <div>
            <label className={fieldLabelClass} htmlFor="receipt-file">
              Receipt
            </label>
            <input
              id="receipt-file"
              type="file"
              accept={ACCEPT}
              className={`${fieldInputClass} py-2`}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setMessage(null)
              }}
            />
            <p className={fieldHintClass}>
              A PDF e-receipt, a screenshot, or a photo of a paper one.
            </p>
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="receipt-store">
              Store (optional)
            </label>
            <input
              id="receipt-store"
              type="text"
              value={storeChain}
              placeholder="Read from the receipt when left empty"
              className={fieldInputClass}
              onChange={(event) => setStoreChain(event.target.value)}
            />
          </div>

          <div>
            <label className={fieldLabelClass} htmlFor="receipt-date">
              Purchase date (optional)
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

          <Button type="submit" size="lg" disabled={!file} loading={upload.isPending}>
            Upload
          </Button>
        </form>
      </main>
    </div>
  )
}
