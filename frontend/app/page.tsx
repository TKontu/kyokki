'use client'

import { useState } from 'react'
import {
  ClearExpiredSheet,
  ConsumptionSheet,
  InventoryList,
  ItemEditSheet,
  QuickAddSheet,
  UndoButton,
} from '@/components/inventory'
import { ReceiptsBanner } from '@/components/receipts'
import Button from '@/components/ui/Button'
import { useConsumeInventoryItem, useInventoryList } from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import type { InventoryItem } from '@/types/inventory'

export default function Home() {
  // Same query key as InventoryList, so this shares its cache instead of refetching.
  const { data: items } = useInventoryList()
  const consume = useConsumeInventoryItem()
  const toast = useToast()
  const [consumingId, setConsumingId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  // Keep the item being edited even after a delete or "gone" drops it from the list, so the
  // sheet can finish (toast, close) before it unmounts.
  const [editing, setEditing] = useState<InventoryItem | null>(null)
  // Held rather than re-derived: the confirm lists exactly what was on offer when it opened,
  // so a background refetch cannot change what the cook is agreeing to throw away.
  const [clearing, setClearing] = useState<InventoryItem[] | null>(null)

  // Read the live cached item so the sheet reflects optimistic and refetched values.
  const consumingItem = items?.find((item) => item.id === consumingId) ?? null
  const editingItem = editing ? items?.find((item) => item.id === editing.id) ?? editing : null
  const startEditing = (id: string) => setEditing(items?.find((item) => item.id === id) ?? null)

  /**
   * A tap on a card's consume button: no sheet, no success toast (operator, 2026-09-22). The
   * quantity bar moves at once, and the header's Undo names what just happened - which is the
   * confirmation, and the way back from a mis-tap. `mutateAsync` so every failed tap reports,
   * not only the last of a quick run.
   */
  const consumeFromCard = (id: string, amount: number) => {
    const name = items?.find((item) => item.id === id)?.product_name ?? 'that'
    consume.mutateAsync({ id, data: { quantity: amount } }).catch((error) => {
      const clientError = isAPIError(error) && error.status < 500 && error.message
      toast.error(clientError ? error.message : `Could not update ${name}`)
    })
  }

  return (
    <div>
      <header className="px-6 py-4 border-b border-ui-border dark:border-ui-dark-border flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Kyokki</h1>
        <div className="flex items-center gap-3">
          <UndoButton />
          <Button onClick={() => setAdding(true)}>+ Add</Button>
        </div>
      </header>
      <main className="px-6 py-4">
        <ReceiptsBanner />
        <InventoryList
          onConsume={consumeFromCard}
          onMore={setConsumingId}
          onClearExpired={setClearing}
        />
      </main>
      <ConsumptionSheet
        item={consumingItem}
        open={consumingItem !== null}
        onClose={() => setConsumingId(null)}
        onEdit={() => {
          if (consumingId) startEditing(consumingId)
          setConsumingId(null)
        }}
      />
      <QuickAddSheet open={adding} onClose={() => setAdding(false)} />
      <ClearExpiredSheet
        items={clearing ?? []}
        open={clearing !== null}
        onClose={() => setClearing(null)}
      />
      <ItemEditSheet
        item={editingItem}
        open={editingItem !== null}
        onClose={() => setEditing(null)}
      />
    </div>
  )
}
