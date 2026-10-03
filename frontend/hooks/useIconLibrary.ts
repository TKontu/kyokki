/**
 * Icon curation (operator ask 2026-10-03): the status check that gates the UI, the
 * marked-icons list for Settings, and the mark/unmark mutations the product sheet uses.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import iconLibraryAPI from '@/lib/api/iconLibrary'
import { productKeys } from '@/hooks/useProducts'

export const iconLibraryKeys = {
  all: ['icon-library'] as const,
  status: () => [...iconLibraryKeys.all, 'status'] as const,
  marks: () => [...iconLibraryKeys.all, 'marks'] as const,
}

/** Whether curation is enabled on this server, and the counts Settings shows. */
export function useIconLibraryStatus() {
  return useQuery({
    queryKey: iconLibraryKeys.status(),
    queryFn: () => iconLibraryAPI.getStatus(),
    staleTime: 30_000,
  })
}

/** Every marked product, for Settings' "Canonical icons" list.
 *
 * `enabled` (default true) lets a caller skip the request entirely - Settings passes its
 * own `curation_enabled` status through here, so the list is never fetched on a server
 * where the section does not even show.
 */
export function useIconLibraryMarks(enabled: boolean = true) {
  return useQuery({
    queryKey: iconLibraryKeys.marks(),
    queryFn: () => iconLibraryAPI.listMarks(),
    staleTime: 10_000,
    enabled,
  })
}

/** A mark changes no stock, so only the icon-library queries and the product itself
 * (the sheet's own toggle, Settings' list and counts) need refreshing - never `inventory`. */
function useInvalidateMarks() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: iconLibraryKeys.all })
    queryClient.invalidateQueries({ queryKey: productKeys.all })
  }
}

/** Mutation: "Keep as canonical" on the product sheet. */
export function useMarkIcon() {
  const invalidate = useInvalidateMarks()
  return useMutation({
    mutationFn: (productId: string) => iconLibraryAPI.markIcon(productId),
    onSuccess: invalidate,
  })
}

/** Mutation: undo a mark. */
export function useUnmarkIcon() {
  const invalidate = useInvalidateMarks()
  return useMutation({
    mutationFn: (productId: string) => iconLibraryAPI.unmarkIcon(productId),
    onSuccess: invalidate,
  })
}
