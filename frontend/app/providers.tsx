'use client'

/**
 * Global Providers
 * Sets up TanStack Query and other client-side providers
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useState } from 'react'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Stale time for always-on iPad display
            staleTime: 30_000, // 30 seconds
            // Refetch on window focus (when user returns to app)
            refetchOnWindowFocus: true,
            // Retry failed requests
            retry: 1,
          },
          mutations: {
            // Retry mutations on network error
            retry: 1,
          },
        },
      })
  )

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {/* Dev tools only in development */}
      {process.env.NODE_ENV === 'development' && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  )
}
