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
 * height left under the app's bar and the fridge fills what the slim row of Undo and + Add
 * leaves, so nothing scrolls on the upright iPad (Q17, Q20).
 */
export default function Home() {
  const { finishItem, openMore, sheets } = useStockActions()
  const [adding, setAdding] = useState(false)
  // Held rather than re-derived: the confirm lists exactly what was on offer when it opened,
  // so a background refetch cannot change what the cook is agreeing to throw away.
  const [clearing, setClearing] = useState<InventoryItem[] | null>(null)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* No visible title (Q20): the app's bar already says where this is, and the height goes
          to the fridge. Undo and + Add keep their full touch size in a slim row. */}
      <header className="flex items-center justify-end gap-3 px-4 pt-2">
        <h1 className="sr-only">Kyokki</h1>
        <UndoButton />
        <Button onClick={() => setAdding(true)}>+ Add</Button>
      </header>
      <main className="flex min-h-0 flex-1 flex-col px-4 pb-3 pt-2">
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
