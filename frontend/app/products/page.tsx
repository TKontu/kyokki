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

import React, { useMemo, useState } from 'react'
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
  useEstimateCatalog,
  useProductList,
} from '@/hooks/useProducts'
import type { EstimateScope } from '@/lib/api/products'
import { auditRows, type AuditRow, type Edge } from '@/lib/shelfLifeAudit'
import type { CatalogEstimateResponse, ProductMaster } from '@/types/product'

type View = 'category' | 'audit'

function shelfLifeNote(product: ProductMaster): { text: string; guess: boolean } {
  const days = `${product.default_shelf_life_days} ${
    product.default_shelf_life_days === 1 ? 'day' : 'days'
  }`
  switch (product.shelf_life_source) {
    case 'cook':
      return { text: `${days} · you set this`, guess: false }
    case 'model':
      return { text: `${days} · estimated`, guess: false }
    default:
      return { text: `${days} · from the category`, guess: true }
  }
}

function sizeNote(product: ProductMaster): string | null {
  if (product.avg_piece_grams) return `one piece ≈ ${product.avg_piece_grams} g`
  if (product.pack_grams) return `one pack ≈ ${product.pack_grams} g`
  return null
}

function ProductRow({
  product,
  onOpen,
}: {
  product: ProductMaster
  onOpen: () => void
}) {
  const shelfLife = shelfLifeNote(product)
  const size = sizeNote(product)

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
            {product.canonical_name}
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
          {product.default_unit}
        </Badge>
      </button>
    </li>
  )
}

function edgeNote(edge: Edge, categoryName: string, band: [number, number]): string {
  const range = `${categoryName} (${band[0]}-${band[1]} days)`
  if (edge === 'outside') return `outside the usual range for ${range}`
  return `near the ${edge === 'short' ? 'shortest' : 'longest'} for ${range}`
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
  return (
    <ul aria-label="Shelf-life audit" className="flex flex-col gap-2">
      {rows.map(({ product, edge, band }) => {
        const shelfLife = shelfLifeNote(product)
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
                  {product.canonical_name}
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
                  {`⚠ ${edgeNote(edge, categoryName(product.category), band)}`}
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
  if (result.applied) return null

  if (result.changes.length === 0) {
    return (
      <p
        role="status"
        className="mb-4 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary"
      >
        {result.considered === 0
          ? scope === 'all'
            ? 'Nothing to estimate: every shelf life is one you set.'
            : 'Nothing to estimate: no product is still using its category default.'
          : `Asked about ${result.considered}; the model agreed with what is already stored.`}
      </p>
    )
  }

  return (
    <section
      aria-label="Proposed shelf lives"
      className="mb-4 rounded-ui border border-ui-border p-4 dark:border-ui-dark-border"
    >
      <p className="text-sm text-ui-text dark:text-ui-dark-text">
        {`${result.changes.length} of ${result.considered} would change. Nothing is saved yet.`}
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
              {`${change.current_days} → ${change.proposed_days} days`}
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex gap-3">
        <Button size="lg" loading={applying} onClick={onApply}>
          {`Save ${result.changes.length}`}
        </Button>
        <Button size="lg" variant="secondary" onClick={onDismiss}>
          Discard
        </Button>
      </div>
    </section>
  )
}

export default function ProductsPage() {
  const [term, setTerm] = useState('')
  const [editing, setEditing] = useState<ProductMaster | null>(null)
  const [proposal, setProposal] = useState<CatalogEstimateResponse | null>(null)
  const [scope, setScope] = useState<EstimateScope>('guesses')
  const [view, setView] = useState<View>('category')
  const search = useDebouncedValue(term, SEARCH_DEBOUNCE_MS)
  const { data: products, isLoading, isError } = useProductList({ search: search || undefined })
  const { data: categories } = useCategories()
  const estimate = useEstimateCatalog()
  const toast = useToast()

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
              ? `, ${result.items_redated} ${
                  result.items_redated === 1 ? 'item' : 'items'
                } re-dated`
              : ''
          toast.success(`Saved ${result.changes.length} shelf lives${redated}`)
        }
      },
      onError: () => toast.error('Could not reach the model'),
    })

  return (
    <div>
      <header className="border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Products</h1>
        <p className="mt-1 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {products === undefined
            ? 'Loading the catalog'
            : `${products.length} ${products.length === 1 ? 'product' : 'products'}` +
              (guesses > 0 ? `, ${guesses} still using a category default` : '')}
        </p>
      </header>

      <main className="px-6 py-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <input
            type="search"
            aria-label="Search products"
            placeholder="Search"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
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
              Estimate the guesses
            </Button>
          )}
          {estimable > 0 && (
            <Button
              variant="secondary"
              loading={dryRunning('all')}
              onClick={() => run(false, 'all')}
            >
              Re-estimate all (keeps yours)
            </Button>
          )}
        </div>

        <div className="mb-4 max-w-md">
          <ChoiceGroup
            label="Show"
            name="products-view"
            className="grid-cols-2"
            value={view}
            options={[
              { value: 'category', label: 'By category' },
              { value: 'audit', label: 'Audit shelf lives' },
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
            Could not load the catalog.
          </p>
        )}
        {products?.length === 0 && (
          <p className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {search
              ? `Nothing matching “${search}”.`
              : 'No products yet. They are created when you confirm a receipt.'}
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
