'use client'

/**
 * One area of the fridge as a grid of tiles (V4, operator ask 2026-09-24).
 *
 * The fridge (`/`) shows an area as coloured dots; tapping it lands here, on its own route so
 * the iPad's back gesture returns to the fridge. Tiles are stalest first and carry no numbers.
 * A tap uses the item up, "…" opens its sheet - the same actions as the fridge's shelf.
 */

import Link from 'next/link'
import { IngredientTile, UndoButton } from '@/components/inventory'
import { useInventoryList } from '@/hooks/useInventory'
import { useStockActions } from '@/hooks/useStockActions'
import { AREAS, buildFridgeView } from '@/lib/fridge'

const BACK =
  'inline-flex min-h-touch items-center gap-1 text-sm font-medium text-ui-text-secondary ' +
  'hover:text-ui-text dark:text-ui-dark-text-secondary dark:hover:text-ui-dark-text'

export default function AreaPage({ params }: { params: { id: string } }) {
  const area = AREAS.find((candidate) => candidate.id === params.id)
  const { isLoading, isError, error } = useInventoryList()
  const { items, finishItem, openMore, sheets } = useStockActions()

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

  const tiles =
    buildFridgeView(items ?? []).areas.find((entry) => entry.area.id === area.id)?.items ?? []

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
                <IngredientTile item={item} onSelect={finishItem} onMore={openMore} />
              </li>
            ))}
          </ul>
        )}
      </main>
      {sheets}
    </div>
  )
}
