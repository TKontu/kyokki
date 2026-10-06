'use client'

/**
 * "Generate shopping list" (AG6 on the iPad; CL6 added "running out soon"): a dry run shows what would be added or raised
 * before anything is written, then "Add to list" applies the same sources for real. Two
 * sources, both on by default (CL6): low stock, and what the run-out forecast says runs out
 * soon - a line that one picked shows the day. Changing them asks for a new preview.
 */

import React, { useEffect, useRef, useState } from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { useGenerateShoppingList } from '@/hooks/useShopping'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { newIdempotencyKey } from '@/lib/api/shopping'
import { formatDate, formatNumber, useT } from '@/lib/i18n'
import { useLanguage } from '@/lib/language'
import type { Language } from '@/lib/language'
import type {
  ShoppingGenerateLine,
  ShoppingGenerateResponse,
  ShoppingGenerateSource,
} from '@/types/shopping'

export interface GenerateSheetProps {
  open: boolean
  onClose: () => void
}

function errorText(error: unknown, fallback: string): string {
  return isAPIError(error) && error.status < 500 && error.message ? error.message : fallback
}

function changeCount(preview: ShoppingGenerateResponse): number {
  return preview.added.length + preview.updated.length
}

/** Every source, in the order the sheet offers (and sends) them. */
const SOURCES: ShoppingGenerateSource[] = ['low_stock', 'runout']
const SOURCE_LABELS: Record<ShoppingGenerateSource, string> = {
  low_stock: 'shopping.generate.lowStock',
  runout: 'shopping.generate.runout',
}

/** One source as a tappable on/off pill built on a real checkbox. */
function SourceToggle({
  checked,
  onChange,
  children,
}: {
  checked: boolean
  onChange: () => void
  children: React.ReactNode
}) {
  return (
    // `relative` keeps the visually hidden input inside its label (as `ChoiceGroup` does).
    <label
      className={`relative flex min-h-touch cursor-pointer items-center justify-center rounded-ui border px-3 text-sm ${
        checked
          ? 'border-ui-text bg-ui-text text-white dark:border-ui-dark-text dark:bg-ui-dark-text dark:text-ui-dark-bg'
          : 'border-ui-border text-ui-text dark:border-ui-dark-border dark:text-ui-dark-text'
      }`}
    >
      <input type="checkbox" className="sr-only" checked={checked} onChange={onChange} />
      {children}
    </label>
  )
}

function LineText({
  line,
  language,
  t,
}: {
  line: ShoppingGenerateLine
  language: Language
  t: (key: string, params?: Record<string, string | number>) => string
}) {
  const need = line.need === null ? '' : formatNumber(line.need, language)
  const date = line.runs_out_on
    ? ` · ${t('shopping.generate.runsOut', { date: formatDate(line.runs_out_on, language) })}`
    : ''
  return <>{`${line.name} · ${need} ${line.unit}${date}`}</>
}

function GenerateForm({ onClose }: { onClose: () => void }) {
  const generate = useGenerateShoppingList()
  const toast = useToast()
  const [language] = useLanguage()
  const { t } = useT()
  const [preview, setPreview] = useState<ShoppingGenerateResponse | null>(null)
  const [sources, setSources] = useState<ShoppingGenerateSource[]>(SOURCES)
  // Only the newest preview counts: a slower answer for sources since changed is dropped.
  const previewRun = useRef(0)
  // F1: one key for the whole apply action. Minted the first time "Add to list" is pressed,
  // and reused by a later press while the sheet is still open - a retry of the same action,
  // not a new one - then forgotten once it succeeds (the sheet closes anyway).
  const applyKey = useRef<string | null>(null)

  useEffect(() => {
    const run = ++previewRun.current
    setPreview(null)
    // Other sources are another action: a retry key minted for the old ones is not reused.
    applyKey.current = null
    if (sources.length === 0) return
    generate.mutate(
      { sources, dry_run: true },
      {
        onSuccess: (result) => {
          if (run === previewRun.current) setPreview(result)
        },
        onError: (error) => {
          if (run !== previewRun.current) return
          toast.error(errorText(error, t('shopping.generate.checkError')))
          onClose()
        },
      }
    )
    // Runs when the sheet mounts, and again whenever the chosen sources change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sources])

  const toggle = (source: ShoppingGenerateSource) =>
    setSources((current) =>
      SOURCES.filter((s) => (s === source ? !current.includes(s) : current.includes(s)))
    )

  const apply = () => {
    if (sources.length === 0) return
    const idempotencyKey = applyKey.current ?? newIdempotencyKey()
    applyKey.current = idempotencyKey
    generate.mutate(
      { sources, dry_run: false, idempotencyKey },
      {
        onSuccess: (result) => {
          applyKey.current = null
          const count = changeCount(result)
          toast.success(
            count > 0
              ? t('shopping.generate.addedToast', { count })
              : t('shopping.generate.nothingToAdd')
          )
          onClose()
        },
        onError: (error) => toast.error(errorText(error, t('shopping.generate.generateError'))),
      }
    )
  }

  const nothingToDo = preview !== null && changeCount(preview) === 0
  const noSource = sources.length === 0

  return (
    <BottomSheet
      open
      onClose={onClose}
      title={t('shopping.generate.title')}
      footer={
        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t('shopping.generate.cancel')}
          </Button>
          <Button
            data-primary
            size="lg"
            disabled={noSource || !preview || nothingToDo}
            loading={generate.isPending}
            onClick={apply}
          >
            {t('shopping.generate.addToList')}
          </Button>
        </div>
      }
    >
      <div
        role="group"
        aria-label={t('shopping.generate.sources')}
        className="mb-4 grid grid-cols-2 gap-2"
      >
        {SOURCES.map((source) => (
          <SourceToggle
            key={source}
            checked={sources.includes(source)}
            onChange={() => toggle(source)}
          >
            {t(SOURCE_LABELS[source])}
          </SourceToggle>
        ))}
      </div>
      {noSource && (
        <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {t('shopping.generate.noSource')}
        </p>
      )}
      {!noSource && !preview && (
        <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {t('shopping.generate.checking')}
        </p>
      )}
      {preview && (
        <div className="flex flex-col gap-4">
          {nothingToDo && preview.skipped.length === 0 && (
            <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
              {t('shopping.generate.nothingShort')}
            </p>
          )}
          {preview.added.length > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                {t('shopping.generate.new')}
              </h3>
              <ul>
                {preview.added.map((line) => (
                  <li key={line.product_id} className="text-ui-text dark:text-ui-dark-text">
                    <LineText line={line} language={language} t={t} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {preview.updated.length > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                {t('shopping.generate.raised')}
              </h3>
              <ul>
                {preview.updated.map((line) => (
                  <li key={line.product_id} className="text-ui-text dark:text-ui-dark-text">
                    <LineText line={line} language={language} t={t} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {preview.skipped.length > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                {t('shopping.generate.skipped')}
              </h3>
              <ul>
                {preview.skipped.map((line) => (
                  <li
                    key={line.product_id}
                    className="text-ui-text-secondary dark:text-ui-dark-text-secondary"
                  >
                    {line.name} · {line.reason}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </BottomSheet>
  )
}

/** Mount the form only while open: it starts fresh (and asks for a new dry run) every time. */
export function GenerateSheet({ open, onClose }: GenerateSheetProps) {
  return open ? <GenerateForm onClose={onClose} /> : null
}

export default GenerateSheet
