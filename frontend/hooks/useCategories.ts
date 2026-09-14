import { useQuery } from '@tanstack/react-query'
import categoriesAPI from '@/lib/api/categories'

export const categoryKeys = {
  all: ['categories'] as const,
}

/** Categories rarely change: cache them for the session. */
export function useCategories() {
  return useQuery({
    queryKey: categoryKeys.all,
    queryFn: () => categoriesAPI.list(),
    staleTime: 10 * 60_000,
  })
}
