'use client'

/**
 * Global Providers
 * Sets up TanStack Query and other client-side providers
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useEffect, useState } from 'react'
import { ToastProvider } from '@/components/ui/Toast'
import { applyLanguage, readLanguage, subscribeToLanguage } from '@/lib/language'
import { applyTheme, readTheme } from '@/lib/theme'
import { useLiveUpdates } from '@/hooks/useLiveUpdates'

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

  // One SSE connection for the whole app (A5): invalidates the right query keys as
  // broadcasts arrive, so inventory/useInventory.ts's poll is a fallback, not the only path.
  useLiveUpdates(queryClient)

  // Re-asserts the stored theme (class and status-bar colour) once hydration has finished.
  // THEME_SCRIPT already applies it before first paint, so this is normally a no-op; it
  // exists so a hydration mismatch elsewhere in the tree - which React recovers from by
  // discarding the server-rendered DOM and re-rendering on the client - cannot silently
  // leave a forced theme reverted (round 2026-09-30-1).
  useEffect(() => {
    applyTheme(readTheme())
  }, [])

  // Keeps <html lang> on the stored display language (frontier item 13 phase 2), the same
  // mount-effect belt-and-braces as the theme above: LANGUAGE_SCRIPT already set it before
  // first paint for everything but the default, and this also follows a later change - this
  // tab's own Settings toggle, or another tab's - without a navigation in between.
  useEffect(() => {
    applyLanguage(readLanguage())
    return subscribeToLanguage(() => applyLanguage(readLanguage()))
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      {/* Inside the query client so mutation hooks can raise toasts */}
      <ToastProvider>
        {children}
        {/* Dev tools only in development */}
        {process.env.NODE_ENV === 'development' && (
          <ReactQueryDevtools initialIsOpen={false} />
        )}
      </ToastProvider>
    </QueryClientProvider>
  )
}
