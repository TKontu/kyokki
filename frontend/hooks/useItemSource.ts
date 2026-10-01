/**
 * useItemSource (Q26)
 * Which receipt line an inventory item came from, for the item's sheet.
 */

import { useQuery } from '@tanstack/react-query'
import inventoryAPI from '@/lib/api/inventory'

export const itemSourceKeys = {
  all: ['item-source'] as const,
  detail: (id: string) => [...itemSourceKeys.all, id] as const,
}

/**
 * Fetches only when `itemId` is given: a hand-added item has no receipt, so the sheet passes
 * `null` for it rather than asking the API for something it already knows the answer to.
 */
export function useItemSource(itemId: string | null) {
  return useQuery({
    queryKey: itemSourceKeys.detail(itemId ?? ''),
    queryFn: () => inventoryAPI.source(itemId as string),
    enabled: Boolean(itemId),
  })
}
