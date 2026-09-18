'use client'

/**
 * Last resort error boundary (H04).
 * Only reached when the root layout itself threw, so it replaces the layout: it has to render
 * its own <html> and <body>, and it cannot use anything the providers supply. Same behaviour as
 * app/error.tsx — retry on a timer, with a button for whoever happens to be there.
 */

import ErrorScreen from '@/components/ui/ErrorScreen'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="en">
      {/* The font variables live on the failed layout, so fall back to the system stack. */}
      <body className="antialiased">
        <ErrorScreen error={error} reset={reset} />
      </body>
    </html>
  )
}
