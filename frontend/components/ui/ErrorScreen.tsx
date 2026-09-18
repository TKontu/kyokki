'use client'

/**
 * What a crash looks like on the kitchen iPad (H04).
 *
 * The screen is always on and nobody is standing at it, so the one thing this must never do is
 * end at a blank page waiting for a tap. It retries itself on a timer; the button is there for
 * when somebody *is* standing at it and does not want to wait.
 */

import React, { useEffect } from 'react'
import Button from '@/components/ui/Button'

/**
 * How long to wait before retrying on our own. Short enough that a backend restart or a dropped
 * Wi-Fi association heals before anyone notices, long enough not to hammer a server that is
 * genuinely down: a failing retry re-mounts this screen and starts the wait again.
 */
export const AUTO_RETRY_MS = 5000

export interface ErrorScreenProps {
  /** The error React caught. `digest` is Next's id for a server-side stack. */
  error: Error & { digest?: string }
  /** Re-renders the failed subtree. Next supplies it; the timer and the button both call it. */
  reset: () => void
  /** Override the retry delay (tests, and callers that want a calmer loop). */
  retryMs?: number
}

export function ErrorScreen({ error, reset, retryMs = AUTO_RETRY_MS }: ErrorScreenProps) {
  useEffect(() => {
    const timer = setTimeout(reset, retryMs)
    return () => clearTimeout(timer)
  }, [reset, retryMs])

  return (
    <div
      role="alert"
      className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 py-10 text-center"
    >
      <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">
        Something went wrong
      </h1>
      <p className="max-w-md text-base text-ui-text-secondary dark:text-ui-dark-text-secondary">
        Kyokki hit an error it could not recover from on its own. It is trying again by itself,
        so you can leave this screen alone.
      </p>
      {/* The message is for whoever is debugging; it is never the only thing on screen. */}
      {error.message && (
        <p className="max-w-md break-words font-mono text-sm text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
          {error.digest ? `${error.message} (${error.digest})` : error.message}
        </p>
      )}
      <Button size="lg" onClick={reset}>
        Try again
      </Button>
    </div>
  )
}

export default ErrorScreen
