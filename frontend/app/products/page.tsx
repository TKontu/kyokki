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
 */

import React, { useMemo, useState } from 'react'
import { ProductEditSheet } from '@/components/products/ProductEditSheet'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { useToast } from '@/hooks/useToast'
import { useCategories } from '@/hooks/useCategories'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import {
  SEARCH_DEBOUNCE_MS,
  useEstimateCatalog,
  useProductList,
} from '@/hooks/useProducts'
import type { CatalogEstimateResponse, ProductMaster } from '@/types/product'

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

/** What a dry run proposed, before any of it is written. */
function ProposedChanges({
  result,
  applying,
  onApply,
  onDismiss,
}: {
  result: CatalogEstimateResponse
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
          ? 'Nothing to estimate: no product is still using its category default.'
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

  const guesses = (products ?? []).filter(
    (product: ProductMaster) => product.shelf_life_source === 'category'
  ).length

  const run = (apply: boolean) =>
    estimate.mutate(apply, {
      onSuccess: (result) => {
        setProposal(result.applied ? null : result)
        if (result.applied) {
          toast.success(`Saved ${result.changes.length} shelf lives`)
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
              loading={estimate.isPending && !estimate.variables}
              onClick={() => run(false)}
            >
              Estimate the guesses
            </Button>
          )}
        </div>

        {proposal && (
          <ProposedChanges
            result={proposal}
            applying={estimate.isPending && Boolean(estimate.variables)}
            onApply={() => run(true)}
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

        <div className="flex flex-col gap-6">
          {grouped.map(([category, items]) => (
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
