'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ConsumptionSheet, InventoryList } from '@/components/inventory'
import { useInventoryList } from '@/hooks/useInventory'
import { useProductList } from '@/hooks/useProducts'

export default function Home() {
  const { data: products, isError: productsError } = useProductList()
  // Same query key as InventoryList, so this shares its cache instead of refetching.
  const { data: items } = useInventoryList()
  const [consumingId, setConsumingId] = useState<string | null>(null)

  const productNames = useMemo(
    () => Object.fromEntries((products ?? []).map((p) => [p.id, p.canonical_name])),
    [products]
  )

  // Read the live cached item so the sheet reflects optimistic and refetched values.
  const consumingItem = items?.find((item) => item.id === consumingId) ?? null

  return (
    <div className="min-h-screen bg-ui-bg dark:bg-ui-dark-bg">
      <header className="px-6 py-4 border-b border-ui-border dark:border-ui-dark-border flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Kyokki</h1>
        <Link
          href="/components-demo"
          className="text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary hover:underline"
        >
          Components
        </Link>
      </header>
      {productsError && (
        <p className="px-6 py-2 text-sm bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 border-b border-yellow-200 dark:border-yellow-800">
          Could not load product names — showing item IDs instead.
        </p>
      )}
      <main className="px-6 py-4">
        <InventoryList productNames={productNames} onConsume={setConsumingId} />
      </main>
      <ConsumptionSheet
        item={consumingItem}
        open={consumingItem !== null}
        onClose={() => setConsumingId(null)}
      />
    </div>
  )
}
