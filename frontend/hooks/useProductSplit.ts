/**
 * useProductSplit (CL8 L3)
 * "This is not X": a wrong join made stew and rice pies one product, so editing one edited the
 * other. These hooks read where a product's items came from and move a group of them onto an
 * existing or new product - and back again.
 *
 * A split (or its undo) moves stock and its history between two products and re-points the
 * printed names, so it refreshes the products, the stock lists and the consumption log.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { consumptionLogKeys } from '@/hooks/useConsumptionLog'
import { inventoryKeys } from '@/hooks/useInventory'
import { productKeys } from '@/hooks/useProducts'
import productsAPI from '@/lib/api/products'
import type { ProductSplitRequest } from '@/types/product'

/** Under `productKeys.all`, so a split's own invalidation refreshes the sources too. */
export const productSourceKeys = {
  detail: (id: string) => [...productKeys.all, 'sources', id] as const,
}

/** Where a product's items came from, grouped. Fetches nothing without a product. */
export function useProductSources(id: string | null) {
  return useQuery({
    queryKey: productSourceKeys.detail(id ?? ''),
    queryFn: () => productsAPI.sources(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  })
}

function useInvalidateSplit() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: productKeys.all })
    queryClient.invalidateQueries({ queryKey: inventoryKeys.all })
    queryClient.invalidateQueries({ queryKey: consumptionLogKeys.all })
  }
}

/** Mutation: move items off a product. Not retried: a 409 is an answer, not a blip. */
export function useSplitProduct() {
  const invalidate = useInvalidateSplit()
  return useMutation({
    mutationFn: ({ productId, body }: { productId: string; body: ProductSplitRequest }) =>
      productsAPI.split(productId, body),
    retry: false,
    onSuccess: invalidate,
  })
}

/** Mutation: reverse a split exactly. 409 `stale` once a moved item changed product since. */
export function useUndoReassignment() {
  const invalidate = useInvalidateSplit()
  return useMutation({
    mutationFn: (reassignmentId: string) => productsAPI.undoReassignment(reassignmentId),
    retry: false,
    onSuccess: invalidate,
  })
}
