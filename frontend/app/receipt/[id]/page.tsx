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
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import { fieldInputClass, fieldLabelClass } from '@/components/ui/formStyles'
import {
  ReceiptItemRow,
  canInclude,
  chosenProductId,
  type ReviewRow,
} from '@/components/receipts/ReceiptItemRow'
import { useCategories } from '@/hooks/useCategories'
import { useConfirmReceipt, useReceipt, useReprocessReceipt } from '@/hooks/useReceipts'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { toISODate } from '@/lib/dates'
import { isStale, readMethod, receiptDate, storeName } from '@/lib/receipts'
import type { Category } from '@/types/category'
import type {
  ConfirmedItemCreate,
  ExtractedItem,
  Receipt,
  ReceiptUnit,
} from '@/types/receipt'

/** An item the read missed altogether, added by hand; confirmed as a free line (Q27). */
interface MissedItem {
  key: number
  name: string
  category: string
  quantity: string
  unit: ReceiptUnit
}

const UNITS: { value: ReceiptUnit; label: string }[] = [
  { value: 'pcs', label: 'pcs' },
  { value: 'g', label: 'g' },
  { value: 'dl', label: 'dl' },
]

/**
 * Whether the read lines differ from the printed total by more than rounding: 1% of the total,
 * and never less than 5 cents in whatever currency the receipt is in. Compared in integer cents,
 * as the backend does, so 0.95 against 1.00 is not a float away from a false alarm.
 */
function totalMismatch(itemsSum: number | null, receiptTotal: number | null): boolean {
  if (itemsSum === null || receiptTotal === null) return false
  const sumCents = Math.round(itemsSum * 100)
  const totalCents = Math.round(receiptTotal * 100)
  return Math.abs(totalCents - sumCents) > Math.max(5, Math.abs(totalCents) * 0.01)
}

/** "1,5" or "1.5" as a number; NaN when it is not one. The iPad's keypad may offer a comma. */
function parseAmount(text: string): number {
  const normalised = text.trim().replace(',', '.')
  return normalised === '' ? NaN : Number(normalised)
}

/**
 * Nine of fifteen lines once vanished between the receipt and this screen without a word (Q27).
 * When the backend had to put lines back, or the read still does not account for the whole
 * receipt, say so, so the cook knows what to check.
 */
function CompletenessBanner({ receipt }: { receipt: Receipt }) {
  const completeness = receipt.completeness
  if (!completeness) return null
  const recovered = completeness.recovered_by_retry + completeness.recovered_raw_lines
  const unaccounted = completeness.unaccounted_lines
  const { items_sum: itemsSum, receipt_total: receiptTotal, text_lines: textLines } = completeness
  const mismatch = totalMismatch(itemsSum, receiptTotal)
  // Unusable entries on their own are not shown: if everything else accounts for the receipt,
  // the entries the model got wrong were not needed, and there is nothing for the cook to do.
  if (recovered <= 0 && unaccounted <= 0 && !mismatch) return null
  const invalid = completeness.invalid_entries
  const one = recovered === 1
  const counted =
    textLines === null
      ? `${recovered} ${one ? 'line' : 'lines'}`
      : `${recovered} of ${textLines} ${textLines === 1 ? 'line' : 'lines'}`
  return (
    <div
      role="status"
      className="mb-4 rounded-ui border border-yellow-400 bg-yellow-50 p-3 text-sm text-yellow-900 dark:border-yellow-700 dark:bg-yellow-950 dark:text-yellow-200"
    >
      {recovered > 0 && (
        <p>
          {`${counted} ${one ? 'was' : 'were'} not read by the model — ` +
            (one
              ? 'it is recovered below, please check it.'
              : 'they are recovered below, please check them.')}
        </p>
      )}
      {unaccounted > 0 && (
        <p>{`${unaccounted} ${unaccounted === 1 ? 'line' : 'lines'} could not be read — see the receipt text.`}</p>
      )}
      {mismatch && itemsSum !== null && receiptTotal !== null && (
        <p>
          {`The items add up to ${itemsSum.toFixed(2)} but the receipt total is ` +
            `${receiptTotal.toFixed(2)} — something may be missing.`}
        </p>
      )}
      {invalid > 0 && (
        <p className="mt-1">
          {`The model's answer had ${invalid} unusable ${invalid === 1 ? 'entry' : 'entries'}.`}
        </p>
      )}
    </div>
  )
}

/**
 * Marks a row the read put back. A raw line asks for a category only while it still needs one:
 * matched to a product, or given a category, it has nothing left to ask.
 */
function RecoveredMarker({ item, row }: { item: ExtractedItem; row: ReviewRow }) {
  if (!item.recovered) return null
  const needsCategory = !chosenProductId(item, row) && row.category === ''
  return (
    <p className="mb-1 flex flex-wrap items-center gap-2 text-sm text-yellow-700 dark:text-yellow-400">
      <span className="rounded-full border border-current px-2 py-0.5 text-xs font-medium">
        recovered
      </span>
      {item.recovered === 'raw_line' && (
        <span>
          {needsCategory ? 'from the receipt text — pick a category' : 'from the receipt text'}
        </span>
      )}
    </p>
  )
}

type MissedDraft = Omit<MissedItem, 'key'>

const EMPTY_MISSED: MissedDraft = { name: '', category: '', quantity: '1', unit: 'pcs' }

/** Confirm needs a name and a category to create a product from a line on no receipt row. */
function draftReady(draft: MissedDraft): boolean {
  return draft.name.trim() !== '' && draft.category !== '' && parseAmount(draft.quantity) > 0
}

/** The last row of the list: name, category and amount for something the read missed. */
function AddMissedItem({
  categories,
  draft,
  onDraftChange,
  onAdd,
}: {
  categories: Category[]
  draft: MissedDraft
  onDraftChange: (draft: MissedDraft) => void
  onAdd: () => void
}) {
  const ready = draftReady(draft)
  const update = (changes: Partial<MissedDraft>) => onDraftChange({ ...draft, ...changes })

  return (
    <section
      aria-label="Add a missed item"
      className="mt-3 rounded-ui border border-dashed border-ui-border p-3 dark:border-ui-dark-border"
    >
      <h2 className="text-base font-medium text-ui-text dark:text-ui-dark-text">
        Add a missed item
      </h2>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1">
          {/* Labelled "Missed item …" rather than "Name"/"Category": the read rows above
              already have fields called that, and each must stay the only one. */}
          <label htmlFor="missed-name" className={fieldLabelClass}>
            Missed item name
          </label>
          <input
            id="missed-name"
            type="text"
            value={draft.name}
            onChange={(event) => update({ name: event.target.value })}
            className={`${fieldInputClass} mt-1`}
          />
        </div>
        <div className="min-w-48 flex-1">
          <label htmlFor="missed-category" className={fieldLabelClass}>
            Missed item category
          </label>
          <select
            id="missed-category"
            value={draft.category}
            onChange={(event) => update({ category: event.target.value })}
            className={`${fieldInputClass} mt-1`}
          >
            <option value="">Pick a category…</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {`${category.icon ?? ''} ${category.display_name}`.trim()}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="w-28">
          <label htmlFor="missed-quantity" className={fieldLabelClass}>
            Missed item amount
          </label>
          {/* Text, not number: a number field turns "1,5" into nothing (Q27). */}
          <input
            id="missed-quantity"
            type="text"
            inputMode="decimal"
            value={draft.quantity}
            onChange={(event) => update({ quantity: event.target.value })}
            className={`${fieldInputClass} mt-1`}
          />
        </div>
        <ChoiceGroup
          label="Missed item unit"
          name="missed-unit"
          options={UNITS}
          value={draft.unit}
          onChange={(unit) => update({ unit })}
          className="w-48 grid-cols-3"
        />
        <Button
          size="lg"
          variant="secondary"
          disabled={!ready}
          onClick={() => {
            if (ready) onAdd()
          }}
        >
          Add to list
        </Button>
      </div>
    </section>
  )
}

/** The text the read worked from, so the cook can check a line against it (Q28). */
function ReceiptText({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-6">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="receipt-text"
        onClick={() => setOpen((shown) => !shown)}
        className="min-h-touch text-sm text-ui-text-secondary underline dark:text-ui-dark-text-secondary"
      >
        {open ? 'Hide receipt text' : 'Show receipt text'}
      </button>
      {/* Always rendered, so aria-controls points at something; hidden while collapsed. */}
      <pre
        id="receipt-text"
        hidden={!open}
        className="mt-2 max-h-96 overflow-auto whitespace-pre rounded-ui border border-ui-border bg-gray-50 p-3 font-mono text-xs text-ui-text dark:border-ui-dark-border dark:bg-gray-900 dark:text-ui-dark-text"
      >
        {text}
      </pre>
    </div>
  )
}

function initialRow(item: ExtractedItem): ReviewRow {
  const name = item.generic_name ?? item.name
  const category = item.suggested_category ?? ''
  return {
    index: item.index,
    // A line with nothing to go on starts skipped rather than silently creating a product
    include: Boolean(item.product_id) || (name.trim() !== '' && category !== ''),
    productName: undefined,
    name,
    category,
    // Not shown (V2, presence not amounts) and so not fixable here: a line read as nothing
    // still goes in as one, rather than blocking the whole receipt on a number nobody sees
    quantity: String(Number(item.quantity) > 0 ? item.quantity : 1),
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
  // null until the cook taps Show/Hide: the fold starts open when it holds a recovered row.
  const [showHousehold, setShowHousehold] = useState<boolean | null>(null)
  // Whether the cook has ever opened the household fold on this receipt. Folding
  // is the model's guess; only a cook who has actually seen the lines can teach
  // anything from them (H08).
  const [householdSeen, setHouseholdSeen] = useState(false)
  // Items the read missed altogether, added by hand (Q27); keyed so one can be removed.
  const [missed, setMissed] = useState<MissedItem[]>([])
  const [nextMissedKey, setNextMissedKey] = useState(1)
  // The one being typed; lives here so confirming cannot silently drop it.
  const [missedDraft, setMissedDraft] = useState<MissedDraft>(EMPTY_MISSED)

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
    // Confirming used to drop the read method entirely, so the one screen you come back to
    // when stock looks wrong could not tell you whether the model had ever run (Q9).
    const method = readMethod(receipt)
    return (
      <Frame>
        <p className="text-ui-text dark:text-ui-dark-text">
          {`${storeName(receipt)}, ${receiptDate(receipt)}: already added to your stock.`}
        </p>
        {method && (
          <p
            className={
              'mt-2 text-sm ' +
              (method.ok
                ? 'text-ui-text-secondary dark:text-ui-dark-text-secondary'
                : 'text-yellow-700 dark:text-yellow-400')
            }
          >
            {method.ok
              ? `It was ${method.label}.`
              : `It was ${method.label}, so names are as printed and nothing was categorised.`}
          </p>
        )}
      </Frame>
    )
  }

  // Only 'completed' means there is something to review. Anything else — 'uploaded' from before
  // the queue existed (MVP-R3), or a status this build has never heard of — used to fall through
  // to the review form and render an empty list with an "Add 0 items" button. Say what is
  // actually going on and offer the one action that can move it along (H04).
  if (status !== 'completed') {
    return (
      <Frame>
        <p role="alert" className="mb-4 text-ui-text dark:text-ui-dark-text">
          {status === 'uploaded'
            ? 'This receipt was never queued to be read.'
            : `This receipt is in a state this app does not know: ${status}.`}
        </p>
        <Button
          size="lg"
          loading={reprocess.isPending}
          onClick={() =>
            reprocess.mutate(receipt.id, {
              onError: () => toast.error('Could not queue this receipt'),
            })
          }
        >
          Read it now
        </Button>
      </Frame>
    )
  }

  // Household lines are folded away rather than scrolled past every week (Q1). Expanding
  // them puts them back as ordinary rows, so a misjudgement is one tap to fix.
  const household = rows.filter(({ item, row }) => item.non_food && !row.include)
  const visible = rows.filter((entry) => !household.includes(entry))
  const included = rows.filter(({ row }) => row.include)
  // The banner promises recovered lines are "below": a recovered line folded away as
  // household would break that, so the fold starts open until the cook says otherwise.
  const foldOpen = showHousehold ?? household.some(({ item }) => Boolean(item.recovered))
  const skipped = visible.length - included.length
  // A missed item filled in but not yet put on the list goes along with the rest, rather
  // than vanishing when the cook taps the footer instead of "Add to list".
  const draftComplete = draftReady(missedDraft)
  const draftStarted = missedDraft.name.trim() !== ''
  const extras: MissedDraft[] = draftComplete
    ? [...missed, { ...missedDraft, name: missedDraft.name.trim() }]
    : missed
  const toAdd = included.length + extras.length
  const purchaseDate = receipt.purchase_date ?? toISODate(new Date())

  const submit = () => {
    if (draftStarted && !draftComplete) {
      toast.error('Finish the missed item or clear its name before confirming')
      return
    }
    const items: ConfirmedItemCreate[] = included.map(({ item, row }) => {
      // The cook's choice on the row wins over whatever the read proposed; detaching
      // (productId: null) sends a name and category instead, and confirm learns the
      // printed name against the product that results (H15).
      const productId = chosenProductId(item, row)
      const base = {
        index: item.index,
        line_id: item.line_id,
        quantity: Number(row.quantity),
        unit: row.unit,
        purchase_date: purchaseDate,
      }
      return productId
        ? { ...base, product_id: productId }
        : { ...base, name: row.name.trim(), category: row.category }
    })
    // A hand-added item is on no receipt line, so it names no line and teaches no alias.
    for (const extra of extras) {
      items.push({
        name: extra.name,
        category: extra.category,
        quantity: parseAmount(extra.quantity),
        unit: extra.unit,
        purchase_date: purchaseDate,
      })
    }

    // Only teach from lines the cook has actually looked at. A misjudgement inside
    // a fold that was never opened would otherwise be remembered forever, hiding a
    // real food line from every future receipt (H08). A fold that is open now was seen.
    const nonFoodIndexes = householdSeen || foldOpen
      ? household.map(({ item }) => item.index)
      : []

    confirm.mutate(
      { id: receipt.id, data: { items, non_food_indexes: nonFoodIndexes } },
      {
        onSuccess: (result) => {
          if (result.items_created === 0) {
            toast.success(`Dismissed · ${storeName(receipt)}`)
          } else {
            const noun = result.items_created === 1 ? 'item' : 'items'
            toast.success(
              `Added ${result.items_created} ${noun} · ${storeName(receipt)}`
            )
          }
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
        {/* A good read used to say nothing at all, so "no warning" and "nobody looked"
            were indistinguishable. Both now say which they were (Q9). */}
        {receipt.extraction_method === 'heuristic' ? (
          <p className="mt-2 text-sm text-yellow-700 dark:text-yellow-400">
            Read without the AI model, so names are as printed.{' '}
            <button
              type="button"
              className="underline"
              onClick={() => reprocess.mutate(receipt.id)}
            >
              Read again with the model
            </button>
          </p>
        ) : (
          readMethod(receipt) && (
            <p className="mt-1 text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
              {readMethod(receipt)?.label}
            </p>
          )
        )}
      </header>

      <main className={`${mainClass} pb-32`}>
        <CompletenessBanner receipt={receipt} />
        <ul className="flex flex-col gap-3">
          {(foldOpen ? rows : visible).map(({ item, row }) => (
            <li key={item.index}>
              <RecoveredMarker item={item} row={row} />
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
        {missed.length > 0 && (
          <ul aria-label="Added by hand" className="mt-3 flex flex-col gap-3">
            {missed.map((extra) => (
              <li
                key={extra.key}
                className="flex items-center justify-between gap-3 rounded-ui border border-ui-border p-3 dark:border-ui-dark-border"
              >
                <div className="min-w-0">
                  <p className="text-base font-medium text-ui-text dark:text-ui-dark-text">
                    {extra.name}
                  </p>
                  <p className="text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
                    {`${sortedCategories.find((c) => c.id === extra.category)?.display_name ?? extra.category} · ${extra.quantity} ${extra.unit} · added by hand`}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="lg"
                  aria-label={`Remove ${extra.name}`}
                  onClick={() =>
                    setMissed((current) => current.filter((other) => other.key !== extra.key))
                  }
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )}
        <AddMissedItem
          categories={sortedCategories}
          draft={missedDraft}
          onDraftChange={setMissedDraft}
          onAdd={() => {
            const extra = { ...missedDraft, name: missedDraft.name.trim() }
            setMissed((current) => [...current, { ...extra, key: nextMissedKey }])
            setNextMissedKey((key) => key + 1)
            setMissedDraft(EMPTY_MISSED)
          }}
        />
        {receipt.ocr_raw_text && <ReceiptText text={receipt.ocr_raw_text} />}
      </main>

      <footer className="fixed inset-x-0 bottom-0 flex items-center justify-between gap-4 border-t border-ui-border bg-white px-6 py-3 pb-[env(safe-area-inset-bottom)] dark:border-ui-dark-border dark:bg-ui-dark-bg">
        <div className="min-w-0 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {/* Expiry is counted from the receipt's own date, not the day of adding - which is
              right, and which means a receipt from months ago silently adds a shelf of expired
              food. Keyed on the receipt date rather than per-item expiry: the client does not
              know a matched product's stored shelf life, only the model's guess for the line,
              so a per-item prediction would be wrong exactly when it mattered (Q10). */}
          {isStale(receipt) && (
            <p role="alert" className="text-yellow-700 dark:text-yellow-400">
              {`This receipt is from ${receiptDate(receipt)} — expiry dates are counted from ` +
                'then, so most items will be added already expired.'}
            </p>
          )}
          <p>{skipped > 0 ? `${skipped} skipped` : 'Nothing skipped'}</p>
          {household.length > 0 && (
            <p className="truncate">
              {`${household.length} household ${household.length === 1 ? 'item' : 'items'} · `}
              {household
                .map(({ item, row }) => row.name || item.generic_name || item.name)
                .join(', ')}
              {' · '}
              <button
                type="button"
                className="underline"
                onClick={() => {
                  setShowHousehold(!foldOpen)
                  setHouseholdSeen(true)
                }}
              >
                {foldOpen ? 'Hide' : 'Show'}
              </button>
            </p>
          )}
        </div>
        <Button
          size="lg"
          disabled={confirm.isPending}
          loading={confirm.isPending}
          onClick={submit}
        >
          {/* Confirming nothing is how an all-household receipt, a duplicate, or a
              read that found no lines gets finished. Without it the receipt stays
              `completed` and the home banner counts it as waiting forever (H08). */}
          {toAdd === 0
            ? 'Dismiss receipt'
            : `Add ${toAdd} ${toAdd === 1 ? 'item' : 'items'}`}
        </Button>
      </footer>
    </div>
  )
}
