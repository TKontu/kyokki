'use client'

/**
 * The catalog (Q11).
 *
 * Until this page the product editor was reachable from exactly one place: an inventory
 * item's edit sheet. So a product you were not currently holding in stock could not be
 * opened at all - 35 of the homelab's 50 - which made "fixed by hand in the product
 * editor", written in HANDOFF.md and docs/TODO.md, quietly untrue since H18 shipped.
 *
 * It also shows which shelf lives are guesses. That is the one number here a cook can act
 * on, and "5 days, from the category" reads very differently from "5 days, you set this".
 *
 * The audit view (H58, Q15) lists the same products by provenance - guesses, then
 * estimates, then the cook's numbers - and flags a number at the edge of its category's
 * plausible range, so a wrong estimate is caught here rather than in a spreadsheet.
 *
 * "Re-estimate all (keeps yours)" (Q19) asks again about every number the cook did not
 * set, earlier estimates included - for after the estimator itself was recalibrated.
 * Same flow as the guesses: a dry run first, then the cook saves what it proposed.
 */

import React, { Suspense, useMemo, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { ProductEditSheet } from '@/components/products/ProductEditSheet'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { useToast } from '@/hooks/useToast'
import { useCategories } from '@/hooks/useCategories'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import {
  SEARCH_DEBOUNCE_MS,
  useConfirmProductEmoji,
  useEstimateCatalog,
  useProductList,
  useRejectProductEmoji,
} from '@/hooks/useProducts'
import { isAPIError } from '@/lib/api/errors'
import type { EstimateScope } from '@/lib/api/products'
import { displayName } from '@/lib/displayName'
import { useT } from '@/lib/i18n'
import { useLanguage } from '@/lib/language'
import { auditRows, type AuditRow, type Edge } from '@/lib/shelfLifeAudit'
import type { CatalogEstimateResponse, ProductMaster } from '@/types/product'

type View = 'category' | 'audit'

type Translate = ReturnType<typeof useT>['t']

function shelfLifeNote(product: ProductMaster, t: Translate): { text: string; guess: boolean } {
  const days = t('products.shelfLife.days', { count: product.default_shelf_life_days })
  switch (product.shelf_life_source) {
    case 'cook':
      return { text: t('products.shelfLife.cook', { days }), guess: false }
    case 'model':
      return { text: t('products.shelfLife.model', { days }), guess: false }
    default:
      return { text: t('products.shelfLife.category', { days }), guess: true }
  }
}

function sizeNote(product: ProductMaster, t: Translate): string | null {
  if (product.avg_piece_grams) return t('products.size.piece', { grams: product.avg_piece_grams })
  if (product.pack_grams) return t('products.size.pack', { grams: product.pack_grams })
  return null
}

/** A unit the catalogue does not know (none today) shows as served, not as its key. */
function unitLabel(unit: string, t: Translate): string {
  const key = `productSheet.units.${unit}`
  const label = t(key)
  return label === key ? unit : label
}

function ProductRow({
  product,
  onOpen,
}: {
  product: ProductMaster
  onOpen: () => void
}) {
  const [language] = useLanguage()
  const { t } = useT()
  const shelfLife = shelfLifeNote(product, t)
  const size = sizeNote(product, t)

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className={
          'flex w-full min-h-touch-lg items-center justify-between gap-3 rounded-ui border ' +
          'border-ui-border px-4 py-3 text-left dark:border-ui-dark-border ' +
          'hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary'
        }
      >
        <span className="min-w-0">
          <span className="block truncate text-base text-ui-text dark:text-ui-dark-text">
            {displayName(product.display_names, product.canonical_name, language)}
          </span>
          <span
            className={
              'block truncate text-sm ' +
              (shelfLife.guess
                ? 'text-yellow-700 dark:text-yellow-400'
                : 'text-ui-text-secondary dark:text-ui-dark-text-secondary')
            }
          >
            {shelfLife.text}
            {size ? ` · ${size}` : ''}
          </span>
        </span>
        <Badge variant="default" size="sm">
          {unitLabel(product.default_unit, t)}
        </Badge>
      </button>
    </li>
  )
}

function edgeNote(
  edge: Edge,
  categoryName: string,
  band: [number, number],
  t: Translate
): string {
  const range = t('products.audit.range', { category: categoryName, min: band[0], max: band[1] })
  if (edge === 'outside') return t('products.audit.outside', { range })
  return t(edge === 'short' ? 'products.audit.nearShortest' : 'products.audit.nearLongest', {
    range,
  })
}

/** Every product by provenance, the ones worth a second look flagged (H58). */
function AuditList({
  rows,
  categoryName,
  onOpen,
}: {
  rows: AuditRow[]
  categoryName: (id: string) => string
  onOpen: (product: ProductMaster) => void
}) {
  const [language] = useLanguage()
  const { t } = useT()
  return (
    <ul aria-label={t('products.audit.label')} className="flex flex-col gap-2">
      {rows.map(({ product, edge, band }) => {
        const shelfLife = shelfLifeNote(product, t)
        return (
          <li key={product.id}>
            <button
              type="button"
              onClick={() => onOpen(product)}
              className={
                'flex w-full min-h-touch-lg flex-col items-start gap-0.5 rounded-ui border ' +
                'border-ui-border px-4 py-3 text-left dark:border-ui-dark-border ' +
                'hover:bg-ui-bg-secondary dark:hover:bg-ui-dark-bg-secondary'
              }
            >
              <span className="flex w-full items-baseline justify-between gap-3">
                <span
                  data-name
                  className="truncate text-base text-ui-text dark:text-ui-dark-text"
                >
                  {displayName(product.display_names, product.canonical_name, language)}
                </span>
                <span className="shrink-0 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
                  {categoryName(product.category)}
                </span>
              </span>
              <span
                className={
                  'text-sm ' +
                  (shelfLife.guess
                    ? 'text-yellow-700 dark:text-yellow-400'
                    : 'text-ui-text-secondary dark:text-ui-dark-text-secondary')
                }
              >
                {shelfLife.text}
              </span>
              {edge && band && (
                <span className="text-sm font-medium text-orange-700 dark:text-orange-400">
                  {`⚠ ${edgeNote(edge, categoryName(product.category), band, t)}`}
                </span>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/** What a dry run proposed, before any of it is written. */
function ProposedChanges({
  result,
  scope,
  applying,
  onApply,
  onDismiss,
}: {
  result: CatalogEstimateResponse
  scope: EstimateScope
  applying: boolean
  onApply: () => void
  onDismiss: () => void
}) {
  const { t } = useT()
  if (result.applied) return null

  if (result.changes.length === 0) {
    return (
      <p
        role="status"
        className="mb-4 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary"
      >
        {result.considered === 0
          ? scope === 'all'
            ? t('products.proposal.nothingAll')
            : t('products.proposal.nothingGuesses')
          : t('products.proposal.agreed', { count: result.considered })}
      </p>
    )
  }

  return (
    <section
      aria-label={t('products.proposal.label')}
      className="mb-4 rounded-ui border border-ui-border p-4 dark:border-ui-dark-border"
    >
      <p className="text-sm text-ui-text dark:text-ui-dark-text">
        {t('products.proposal.wouldChange', {
          changed: result.changes.length,
          count: result.considered,
        })}
      </p>
      <ul className="mt-3 flex flex-col gap-1">
        {result.changes.map((change) => (
          <li
            key={change.id}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <span className="truncate text-ui-text dark:text-ui-dark-text">
              {change.canonical_name}
            </span>
            <span className="shrink-0 text-ui-text-secondary dark:text-ui-dark-text-secondary">
              {t('products.proposal.change', {
                from: change.current_days,
                to: change.proposed_days,
              })}
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex gap-3">
        <Button size="lg" loading={applying} onClick={onApply}>
          {t('products.proposal.save', { count: result.changes.length })}
        </Button>
        <Button size="lg" variant="secondary" onClick={onDismiss}>
          {t('products.proposal.discard')}
        </Button>
      </div>
    </section>
  )
}

/** Every product with a proposal waiting (Q18 build), one tap to confirm or reject. */
function EmojiReviewList({ products }: { products: ProductMaster[] }) {
  const confirm = useConfirmProductEmoji()
  const reject = useRejectProductEmoji()
  const toast = useToast()
  const { t } = useT()

  if (products.length === 0) return null

  const onError = (error: unknown, fallback: string) => {
    const readable = isAPIError(error) && error.status < 500 && error.message
    toast.error(readable ? error.message : fallback)
  }

  return (
    <section
      aria-label={t('products.emojiReview.label')}
      className="mb-4 rounded-ui border border-ui-border p-4 dark:border-ui-dark-border"
    >
      <h2 className="text-sm font-medium text-ui-text dark:text-ui-dark-text">
        {t('products.emojiReview.heading', { count: products.length })}
      </h2>
      <ul className="mt-2 flex flex-col gap-2">
        {products.map((product) => (
          <li key={product.id} className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <span aria-hidden="true" className="text-2xl leading-none">
                {product.emoji}
              </span>
              <span className="truncate text-ui-text dark:text-ui-dark-text">
                {product.canonical_name}
              </span>
            </span>
            <span className="flex shrink-0 gap-2">
              <Button
                size="sm"
                loading={confirm.isPending && confirm.variables === product.id}
                onClick={() =>
                  confirm.mutate(product.id, {
                    onError: (error) => onError(error, t('products.emojiReview.confirmError')),
                  })
                }
              >
                {t('products.emojiReview.confirm')}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                loading={reject.isPending && reject.variables === product.id}
                onClick={() =>
                  reject.mutate(product.id, {
                    onError: (error) => onError(error, t('products.emojiReview.rejectError')),
                  })
                }
              >
                {t('products.emojiReview.reject')}
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function ProductsPage() {
  // `useSearchParams` (the `?q=` filter, below) opts the page out of static rendering unless
  // it sits under its own Suspense boundary - Next.js's own requirement, not a loading state
  // this page ever actually shows (the search params are available on the client at once).
  return (
    <Suspense fallback={null}>
      <ProductsPageContent />
    </Suspense>
  )
}

function ProductsPageContent() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  // The audit view's item links land here with `?q=<name>` (H58 friction, 2026-10-01): the
  // page reads it as its initial filter, and the URL follows what the cook types - replaced,
  // not pushed, so typing does not fill the browser's back history with one entry per letter.
  const [term, setTerm] = useState(() => searchParams.get('q') ?? '')
  const [editing, setEditing] = useState<ProductMaster | null>(null)
  const [proposal, setProposal] = useState<CatalogEstimateResponse | null>(null)
  const [scope, setScope] = useState<EstimateScope>('guesses')
  const [view, setView] = useState<View>('category')
  const search = useDebouncedValue(term, SEARCH_DEBOUNCE_MS)

  const setTermAndUrl = (value: string) => {
    setTerm(value)
    const params = new URLSearchParams(searchParams.toString())
    if (value) params.set('q', value)
    else params.delete('q')
    const query = params.toString()
    router.replace(query ? `${pathname}?${query}` : pathname)
  }
  const { data: products, isLoading, isError } = useProductList({ search: search || undefined })
  const { data: categories } = useCategories()
  const estimate = useEstimateCatalog()
  const toast = useToast()
  const { t } = useT()
  // The review list (Q18 build): a proposal is never shown on a tile until confirmed here.
  const { data: proposedEmoji } = useProductList({ emoji_match: 'proposed' })

  const categoryName = useMemo(() => {
    const names = new Map((categories ?? []).map((c) => [c.id, c.display_name]))
    return (id: string) => names.get(id) ?? id
  }, [categories])

  const grouped = useMemo(() => {
    const groups = new Map<string, ProductMaster[]>()
    for (const product of products ?? []) {
      const existing = groups.get(product.category)
      if (existing) existing.push(product)
      else groups.set(product.category, [product])
    }
    return Array.from(groups.entries()).sort(([a], [b]) =>
      categoryName(a).localeCompare(categoryName(b))
    )
  }, [products, categoryName])

  const audit = useMemo(
    () => auditRows(products ?? [], categories ?? []),
    [products, categories]
  )

  const guesses = (products ?? []).filter(
    (product: ProductMaster) => product.shelf_life_source === 'category'
  ).length

  // Everything an estimate may replace: the guesses and the model's own answers (Q19)
  const estimable = (products ?? []).filter(
    (product: ProductMaster) => product.shelf_life_source !== 'cook'
  ).length

  const dryRunning = (which: EstimateScope) =>
    estimate.isPending && estimate.variables?.scope === which && !estimate.variables.apply

  const run = (apply: boolean, which: EstimateScope) =>
    estimate.mutate({ apply, scope: which }, {
      onSuccess: (result) => {
        setScope(which)
        setProposal(result.applied ? null : result)
        if (result.applied) {
          // Say what happened to the food, not just to the catalog (Q12): a corrected
          // shelf life re-dates the stock that was dated by the old one.
          const redated =
            result.items_redated > 0
              ? t('products.toast.redated', { count: result.items_redated })
              : ''
          toast.success(t('products.toast.saved', { count: result.changes.length, redated }))
        }
      },
      onError: () => toast.error(t('products.toast.modelError')),
    })

  return (
    <div>
      <header className="border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">
          {t('products.title')}
        </h1>
        <p className="mt-1 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {products === undefined
            ? t('products.loading')
            : t('products.count', { count: products.length }) +
              (guesses > 0 ? t('products.guessesSuffix', { count: guesses }) : '')}
        </p>
      </header>

      <main className="px-6 py-4">
        <EmojiReviewList products={proposedEmoji ?? []} />

        <div className="mb-4 flex flex-wrap items-center gap-3">
          <input
            type="search"
            aria-label={t('products.searchLabel')}
            placeholder={t('products.searchPlaceholder')}
            value={term}
            onChange={(event) => setTermAndUrl(event.target.value)}
            className={
              'min-h-touch flex-1 rounded-ui border border-ui-border px-3 py-2 ' +
              'dark:border-ui-dark-border dark:bg-ui-dark-bg-secondary ' +
              'dark:text-ui-dark-text'
            }
          />
          {guesses > 0 && (
            <Button
              variant="secondary"
              loading={dryRunning('guesses')}
              onClick={() => run(false, 'guesses')}
            >
              {t('products.estimateGuesses')}
            </Button>
          )}
          {estimable > 0 && (
            <Button
              variant="secondary"
              loading={dryRunning('all')}
              onClick={() => run(false, 'all')}
            >
              {t('products.reestimateAll')}
            </Button>
          )}
        </div>

        <div className="mb-4 max-w-md">
          <ChoiceGroup
            label={t('products.view.label')}
            name="products-view"
            className="grid-cols-2"
            value={view}
            options={[
              { value: 'category', label: t('products.view.category') },
              { value: 'audit', label: t('products.view.audit') },
            ]}
            onChange={setView}
          />
        </div>

        {proposal && (
          <ProposedChanges
            result={proposal}
            scope={scope}
            applying={estimate.isPending && Boolean(estimate.variables?.apply)}
            onApply={() => run(true, scope)}
            onDismiss={() => setProposal(null)}
          />
        )}

        {isLoading && <SkeletonCard />}
        {isError && (
          <p role="alert" className="text-ui-text dark:text-ui-dark-text">
            {t('products.loadError')}
          </p>
        )}
        {products?.length === 0 && (
          <p className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {search
              ? t('products.nothingMatching', { term: search })
              : t('products.empty')}
          </p>
        )}

        {view === 'audit' && (products?.length ?? 0) > 0 && (
          <AuditList rows={audit} categoryName={categoryName} onOpen={setEditing} />
        )}

        <div className="flex flex-col gap-6">
          {view === 'category' && grouped.map(([category, items]) => (
            <section key={category}>
              <h2 className="mb-2 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                {categoryName(category)}
              </h2>
              <ul className="flex flex-col gap-2">
                {items.map((product) => (
                  <ProductRow
                    key={product.id}
                    product={product}
                    onOpen={() => setEditing(product)}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      </main>

      {editing && (
        <ProductEditSheet product={editing} onClose={() => setEditing(null)} />
      )}
    </div>
  )
}
