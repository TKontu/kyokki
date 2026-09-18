import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import productsAPI from '@/lib/api/products'
import type { ProductListParams } from '@/types/product'

export const productKeys = {
  all: ['products'] as const,
  lists: () => [...productKeys.all, 'list'] as const,
  list: (params?: ProductListParams) => [...productKeys.lists(), params] as const,
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
