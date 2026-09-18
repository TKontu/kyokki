import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import productsAPI from '@/lib/api/products'
import type { ProductListParams, ProductMasterUpdate } from '@/types/product'

export const productKeys = {
  all: ['products'] as const,
  lists: () => [...productKeys.all, 'list'] as const,
  list: (params?: ProductListParams) => [...productKeys.lists(), params] as const,
  detail: (id: string) => [...productKeys.all, 'detail', id] as const,
}

/** One product, for the editor: a stock row only carries the product's name. */
export function useProduct(id: string | null) {
  return useQuery({
    queryKey: productKeys.detail(id ?? ''),
    queryFn: () => productsAPI.get(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  })
}

export function useProductList(params?: ProductListParams) {
  return useQuery({
    queryKey: productKeys.list(params),
    queryFn: () => productsAPI.list(params),
    staleTime: 5 * 60_000,
  })
}

/** How long typing has to pause before a search goes out. Exported so tests step over it
 *  with fake timers instead of waiting on the wall clock (H06). */
export const SEARCH_DEBOUNCE_MS = 250

/** Products whose name contains the term; waits for typing to pause, skips empty terms. */
export function useProductSearch(term: string) {
  const search = useDebouncedValue(term.trim(), SEARCH_DEBOUNCE_MS)
  return useQuery({
    queryKey: productKeys.list({ search }),
    queryFn: () => productsAPI.list({ search }),
    enabled: search.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

/**
 * Mutation: correct a product.
 *
 * The only safe answer to a wrong first guess. A product's shelf life, piece weight
 * and unit are learned from the first receipt that created it, and before this there
 * was no way to fix any of them (H18).
 */
export function useUpdateProduct() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProductMasterUpdate }) =>
      productsAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productKeys.all })
      // Stock rows show the product's name, so they are stale too.
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
    },
  })
}
