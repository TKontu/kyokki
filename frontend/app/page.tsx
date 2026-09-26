'use client'

import { useState } from 'react'
import { ClearExpiredSheet, FridgeView, QuickAddSheet, UndoButton } from '@/components/inventory'
import { ReceiptsBanner } from '@/components/receipts'
import Button from '@/components/ui/Button'
import { useStockActions } from '@/hooks/useStockActions'
import type { InventoryItem } from '@/types/inventory'

/**
 * The stock screen, drawn as a fridge (V3). A tile tap uses the item up and "…" opens its
 * sheet (`useStockActions`); an area opens its own grid at `/area/[id]`. The page takes the
 * height left under the app's bar and the fridge fills what its header leaves, so nothing
 * scrolls on the upright iPad (Q17).
 */
export default function Home() {
  const { finishItem, openMore, sheets } = useStockActions()
  const [adding, setAdding] = useState(false)
  // Held rather than re-derived: the confirm lists exactly what was on offer when it opened,
  // so a background refetch cannot change what the cook is agreeing to throw away.
  const [clearing, setClearing] = useState<InventoryItem[] | null>(null)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="px-6 py-2 border-b border-ui-border dark:border-ui-dark-border flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Kyokki</h1>
        <div className="flex items-center gap-3">
          <UndoButton />
          <Button onClick={() => setAdding(true)}>+ Add</Button>
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col px-4 py-3">
        <ReceiptsBanner />
        <FridgeView onConsume={finishItem} onMore={openMore} onClearExpired={setClearing} />
      </main>
      {sheets}
      <QuickAddSheet open={adding} onClose={() => setAdding(false)} />
      <ClearExpiredSheet
        items={clearing ?? []}
        open={clearing !== null}
        onClose={() => setClearing(null)}
      />
    </div>
  )
}
