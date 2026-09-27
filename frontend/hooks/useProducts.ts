import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import productsAPI, { type EstimateScope } from '@/lib/api/products'
import type { ProductListParams, ProductMasterUpdate } from '@/types/product'

export const productKeys = {
  all: ['products'] as const,
  lists: () => [...productKeys.all, 'list'] as const,
  list: (params?: ProductListParams) => [...productKeys.lists(), params] as const,
  detail: (id: string) => [...productKeys.all, 'detail', id] as const,
  names: (id: string) => [...productKeys.all, 'names', id] as const,
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

/**
 * Products whose name contains the term; waits for typing to pause, skips empty terms.
 *
 * `settled` says the rows on hand are the answer **for this word**: not still debouncing, not
 * in flight, and not the previous term's rows held over by `keepPreviousData`. Offering to
 * create a product before then is how duplicates got made (H25).
 */
export function useProductSearch(term: string) {
  const trimmed = term.trim()
  const search = useDebouncedValue(trimmed, SEARCH_DEBOUNCE_MS)
  const query = useQuery({
    queryKey: productKeys.list({ search }),
    queryFn: () => productsAPI.list({ search }),
    enabled: search.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
  return {
    ...query,
    settled:
      search === trimmed && !query.isFetching && !query.isPlaceholderData && !query.isPending,
  }
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

/** One catalog estimate run: a dry run or an apply, over guesses or everything (Q19). */
export interface EstimateRun {
  apply: boolean
  scope: EstimateScope
}

/**
 * Ask the model about the catalog's shelf lives (Q11): the guesses, or with
 * `scope: 'all'` everything the cook has not set (Q19).
 *
 * A dry run proposes and changes nothing, so only an applied run invalidates. The
 * model call takes the better part of a minute for a whole catalog, and retrying it
 * would double that for no benefit.
 */
export function useEstimateCatalog() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ apply, scope }: EstimateRun) => productsAPI.estimate(apply, scope),
    retry: false,
    onSuccess: (result) => {
      if (!result.applied) return
      queryClient.invalidateQueries({ queryKey: productKeys.all })
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
    },
  })
}

/** The names that resolve to a product, for the editor's list (H52). */
export function useProductNames(id: string | null) {
  return useQuery({
    queryKey: productKeys.names(id ?? ''),
    queryFn: () => productsAPI.names(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
  })
}

/**
 * Mutation: forget a learned name or a printed receipt name (H52).
 *
 * The cleanup for keys a model guess wrote before H51: once "ketchup" stops meaning Taco
 * sauce, the next ketchup line goes back through selection.
 */
export function useForgetName(productId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ kind, id }: { kind: 'name' | 'printed'; id: string }) =>
      kind === 'name'
        ? productsAPI.forgetName(productId, id)
        : productsAPI.forgetPrintedName(productId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: productKeys.names(productId) })
    },
  })
}

/** Refresh what shows a product's icon: the product itself and the tiles (Q18). */
function useInvalidateIcon() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: productKeys.all })
    queryClient.invalidateQueries({ queryKey: ['inventory'] })
  }
}

/**
 * Mutation: draw the product's icon again (Q18), optionally with the cook's hint.
 *
 * Answers at once with the product pending; the drawing lands minutes later and the
 * inventory poll brings it to the tiles. Not retried: each call queues another drawing.
 */
export function useRedrawProductIcon() {
  const invalidate = useInvalidateIcon()
  return useMutation({
    mutationFn: ({ id, hint }: { id: string; hint?: string | null }) =>
      productsAPI.redrawIcon(id, hint),
    retry: false,
    onSuccess: invalidate,
  })
}

/** Mutation: use the category emoji instead of the drawing (Q18). */
export function useClearProductIcon() {
  const invalidate = useInvalidateIcon()
  return useMutation({
    mutationFn: (id: string) => productsAPI.clearIcon(id),
    onSuccess: invalidate,
  })
}
