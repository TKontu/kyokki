'use client'

/**
 * One area of the fridge as a grid of tiles (V4, operator ask 2026-09-24).
 *
 * The fridge (`/`) shows an area as coloured dots; tapping it lands here, on its own route so
 * the iPad's back gesture returns to the fridge. Tiles are stalest first and carry no numbers.
 * A tap uses the item up and leaves a grey tile for a day, so a mis-tap can be taken back with
 * another; "…" opens its sheet.
 */

import Link from 'next/link'
import { useState } from 'react'
import { IngredientTile, UndoButton } from '@/components/inventory'
import { useStockActions } from '@/hooks/useStockActions'
import { AREAS, areaTiles } from '@/lib/fridge'

const BACK =
  'inline-flex min-h-touch items-center gap-1 text-sm font-medium text-ui-text-secondary ' +
  'hover:text-ui-text dark:text-ui-dark-text-secondary dark:hover:text-ui-dark-text'

/** How long a used-up item stays on offer as a grey tile. */
const RECENT_MS = 24 * 60 * 60 * 1000

/** A day back from now, to the hour, so the list's query key holds still between renders. */
function aDayAgo(): string {
  const hour = 60 * 60 * 1000
  return new Date(Math.floor((Date.now() - RECENT_MS) / hour) * hour).toISOString()
}

export default function AreaPage({ params }: { params: { id: string } }) {
  const area = AREAS.find((candidate) => candidate.id === params.id)
  const [since] = useState(aDayAgo)
  const { list, items, toggleItem, openMore, sheets } = useStockActions({ consumed_since: since })
  const { isLoading, isError, error } = list

  if (!area) {
    return (
      <main className="px-6 py-4">
        <Link href="/" className={BACK}>
          ← Fridge
        </Link>
        <p className="mt-4 text-ui-text dark:text-ui-dark-text">No such part of the fridge.</p>
      </main>
    )
  }

  const tiles = areaTiles(items ?? [], area.id)

  return (
    <div>
      <header className="flex items-center justify-between gap-3 border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <div className="flex items-center gap-4">
          <Link href="/" className={BACK}>
            ← Fridge
          </Link>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-ui-text dark:text-ui-dark-text">
            <span aria-hidden="true">{area.icon}</span>
            {area.label}
          </h1>
        </div>
        <UndoButton />
      </header>
      <main className="px-6 py-4">
        {isLoading && <p aria-label="Loading inventory" className="h-32 animate-pulse rounded-2xl bg-gray-200 dark:bg-gray-700" />}
        {isError && !items && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error instanceof Error ? error.message : 'Failed to load inventory.'}
          </p>
        )}
        {items && tiles.length === 0 && (
          <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
            Nothing here.
          </p>
        )}
        {tiles.length > 0 && (
          <ul
            aria-label={area.label}
            className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6"
          >
            {tiles.map((item) => (
              <li key={item.id}>
                <IngredientTile
                  item={item}
                  onSelect={toggleItem}
                  // A grey tile is only for bringing back: its sheet would offer nothing to do
                  onMore={item.status === 'empty' ? undefined : openMore}
                />
              </li>
            ))}
          </ul>
        )}
      </main>
      {sheets}
    </div>
  )
}
