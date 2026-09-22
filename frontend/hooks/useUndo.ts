/**
 * useUndo (operator, 2026-09-22)
 * One general undo: the most recent change to stock, and again for the one before.
 *
 * The preview's key lives under `consumptionLogKeys.all`, so every inventory mutation that
 * writes to the history - consume, discard, restore, correct - already refreshes it.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consumptionLogKeys } from '@/hooks/useConsumptionLog'
import { inventoryKeys } from '@/hooks/useInventory'
import inventoryAPI from '@/lib/api/inventory'
import type { UndoPreview } from '@/types/consumption'

export const undoKeys = {
  preview: () => [...consumptionLogKeys.all, 'undo'] as const,
}

/** What the next undo would reverse, or null. */
export function useUndoPreview() {
  return useQuery<UndoPreview | null>({
    queryKey: undoKeys.preview(),
    queryFn: () => inventoryAPI.undoPreview(),
  })
}

/** Undo the batch the preview showed. Success or refusal, everything it touched is refetched. */
export function useUndo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (batchId: string) => inventoryAPI.undo(batchId),
    // Not idempotent in the way a retry would need: a second attempt after a lost response
    // would be refused as stale at best, and at worst undo the step before as well.
    retry: false,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.all })
      queryClient.invalidateQueries({ queryKey: consumptionLogKeys.all })
    },
  })
}
