'use client'

import { useState } from 'react'
import Link from 'next/link'
import {
  ConsumptionSheet,
  InventoryList,
  ItemEditSheet,
  QuickAddSheet,
} from '@/components/inventory'
import Button from '@/components/ui/Button'
import { useInventoryList } from '@/hooks/useInventory'
import type { InventoryItem } from '@/types/inventory'

export default function Home() {
  // Same query key as InventoryList, so this shares its cache instead of refetching.
  const { data: items } = useInventoryList()
  const [consumingId, setConsumingId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  // Keep the item being edited even after a delete or "gone" drops it from the list, so the
  // sheet can finish (toast, close) before it unmounts.
  const [editing, setEditing] = useState<InventoryItem | null>(null)

  // Read the live cached item so the sheet reflects optimistic and refetched values.
  const consumingItem = items?.find((item) => item.id === consumingId) ?? null
  const editingItem = editing ? items?.find((item) => item.id === editing.id) ?? editing : null
  const startEditing = (id: string) => setEditing(items?.find((item) => item.id === id) ?? null)

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
        <InventoryList onConsume={setConsumingId} onEdit={startEditing} />
      </main>
      <ConsumptionSheet
        item={consumingItem}
        open={consumingItem !== null}
        onClose={() => setConsumingId(null)}
      />
      <QuickAddSheet open={adding} onClose={() => setAdding(false)} />
      <ItemEditSheet
        item={editingItem}
        open={editingItem !== null}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}
