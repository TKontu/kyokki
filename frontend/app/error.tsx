'use client'

/**
 * Route-level error boundary (H04).
 * Catches a render or data error anywhere under the root layout, so a thrown lookup on one card
 * can no longer blank the whole stock page. The layout, and with it the providers and the app
 * shell, stay mounted; see app/global-error.tsx for the case where the layout itself failed.
 */

import ErrorScreen from '@/components/ui/ErrorScreen'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return <ErrorScreen error={error} reset={reset} />
}
