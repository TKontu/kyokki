'use client'

/**
 * FridgeView (V3, operator ask 2026-09-24).
 *
 * The stock screen drawn as a fridge. A shelf across the top holds what is going stale, as
 * tiles you can tap; below it the fridge body has an area per kind of food, and the pantry and
 * freezer are compartments of their own. An area shows its items as coloured dots - one per
 * item, in its staleness colour - rather than a count: nothing on this screen is a number.
 */

import Link from 'next/link'
import React from 'react'
import { useInventoryList } from '@/hooks/useInventory'
import { buildFridgeView, type Area } from '@/lib/fridge'
import { STALENESS, stalenessOf } from '@/lib/staleness'
import type { InventoryItem } from '@/types/inventory'
import { IngredientTile } from './IngredientTile'

export interface FridgeViewProps {
  /** A tap on a tile: the item is used up. */
  onConsume?: (id: string) => void
  onMore?: (id: string) => void
  /** Offered on the shelf when something is past its date. */
  onClearExpired?: (items: InventoryItem[]) => void
}

const EMPTY_MESSAGE =
  'No items found. Add one with + Add, or share a receipt to the Telegram bot - you can also ' +
  'scan one on the Scan screen.'

function Dots({ items }: { items: InventoryItem[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">Empty</p>
    )
  }
  return (
    <div
      role="img"
      aria-label={items
        .map((item) => `${item.product_name} ${STALENESS[stalenessOf(item)].label}`)
        .join(', ')}
      className="flex flex-wrap gap-1.5"
    >
      {items.map((item) => (
        <span
          key={item.id}
          className={`h-3.5 w-3.5 rounded-full ${STALENESS[stalenessOf(item)].dot}`}
        />
      ))}
    </div>
  )
}

function AreaCard({ area, items }: { area: Area; items: InventoryItem[] }) {
  return (
    <section
      aria-label={area.label}
      className="flex min-h-[6rem] flex-col rounded-2xl border border-ui-border bg-ui-bg p-3 dark:border-ui-dark-border dark:bg-ui-dark-bg"
    >
      <Link
        href={`/area/${area.id}`}
        aria-label={`Open ${area.label}`}
        className="flex flex-1 flex-col gap-2 rounded-xl focus:outline-none focus-visible:ring-2"
      >
        <h3 className="flex items-center gap-2 text-base font-semibold text-ui-text dark:text-ui-dark-text">
          <span aria-hidden="true">{area.icon}</span>
          {area.label}
        </h3>
        <Dots items={items} />
      </Link>
    </section>
  )
}

export function FridgeView({ onConsume, onMore, onClearExpired }: FridgeViewProps) {
  const { data: items, isLoading, isError, error } = useInventoryList()

  if (isLoading) {
    return (
      <div className="space-y-3" aria-label="Loading inventory">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-32 animate-pulse rounded-2xl bg-gray-200 dark:bg-gray-700"
            aria-hidden="true"
          />
        ))}
      </div>
    )
  }

  // Only when there is nothing to show instead: the stock already on screen is still the best
  // answer anyone has, and the header's banner says how old it is (H45).
  if (isError && !items) {
    return (
      <p role="alert" className="py-4 text-sm text-red-600 dark:text-red-400">
        {error instanceof Error ? error.message : 'Failed to load inventory.'}
      </p>
    )
  }

  const view = buildFridgeView(items ?? [])
  if (view.areas.every(({ items: inArea }) => inArea.length === 0)) {
    return (
      <p className="py-4 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
        {EMPTY_MESSAGE}
      </p>
    )
  }

  const inFridge = view.areas.filter(({ area }) => area.compartment === 'fridge')
  const below = view.areas.filter(
    ({ area, items: inArea }) =>
      area.compartment === 'pantry' ||
      area.compartment === 'freezer' ||
      (area.compartment === 'other' && inArea.length > 0)
  )

  return (
    <div className="space-y-4">
      {view.goingStale.length > 0 && (
        <section
          aria-label="Going stale"
          className="rounded-2xl border-2 border-red-200 bg-red-50/60 p-3 dark:border-red-900 dark:bg-red-950/30"
        >
          <h2 className="mb-3 flex items-center gap-2 text-base font-semibold text-red-700 dark:text-red-300">
            Going stale
            {onClearExpired && view.expired.length > 0 && (
              <button
                type="button"
                onClick={() => onClearExpired(view.expired)}
                className="ml-auto text-sm font-medium text-red-700 underline dark:text-red-400"
              >
                Clear expired
              </button>
            )}
          </h2>
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {view.goingStale.map((item) => (
              <li key={item.id}>
                <IngredientTile item={item} onSelect={onConsume} onMore={onMore} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="rounded-[2rem] border-4 border-ui-border bg-ui-bg-secondary p-3 dark:border-ui-dark-border dark:bg-ui-dark-bg-secondary">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
          {inFridge.map(({ area, items: inArea }) => (
            <AreaCard key={area.id} area={area} items={inArea} />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {below.map(({ area, items: inArea }) => (
          <AreaCard key={area.id} area={area} items={inArea} />
        ))}
      </div>
    </div>
  )
}

export default FridgeView
