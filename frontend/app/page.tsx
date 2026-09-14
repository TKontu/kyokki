'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ConsumptionSheet, InventoryList, QuickAddSheet } from '@/components/inventory'
import Button from '@/components/ui/Button'
import { useInventoryList } from '@/hooks/useInventory'

export default function Home() {
  // Same query key as InventoryList, so this shares its cache instead of refetching.
  const { data: items } = useInventoryList()
  const [consumingId, setConsumingId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  // Read the live cached item so the sheet reflects optimistic and refetched values.
  const consumingItem = items?.find((item) => item.id === consumingId) ?? null

  return (
    <div className="min-h-screen bg-ui-bg dark:bg-ui-dark-bg">
      <header className="px-6 py-4 border-b border-ui-border dark:border-ui-dark-border flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Kyokki</h1>
        <div className="flex items-center gap-4">
          <Link
            href="/components-demo"
            className="text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary hover:underline"
          >
            Components
          </Link>
          <Button onClick={() => setAdding(true)}>+ Add</Button>
        </div>
      </header>
      <main className="px-6 py-4">
        <InventoryList onConsume={setConsumingId} />
      </main>
      <ConsumptionSheet
        item={consumingItem}
        open={consumingItem !== null}
        onClose={() => setConsumingId(null)}
      />
      <QuickAddSheet open={adding} onClose={() => setAdding(false)} />
    </div>
  )
}
