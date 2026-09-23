'use client'

/**
 * StatusBanner (H45)
 *
 * The iPad sits on a wall with nobody watching it, and until now it could not say when it was
 * out of touch: a failed poll blanked the list, a failed tap left a toast that was gone in five
 * seconds, and stale stock looked exactly like fresh stock.
 *
 * So: one line, above every screen, that speaks **only** when something is wrong. A banner that
 * is always there is a banner nobody reads.
 */

import React from 'react'
import Button from '@/components/ui/Button'
import { useBackendStatus, STALE_AFTER_MS } from '@/hooks/useBackendStatus'
import { useFailedActions } from '@/hooks/useFailedActions'
import { formatAgo } from '@/lib/dates'
import { useQueryClient } from '@tanstack/react-query'

/** Enough to show what went wrong without becoming a list to read. */
const MAX_SHOWN = 3

const boxClass =
  'flex min-h-touch flex-wrap items-center gap-x-3 gap-y-2 border-b px-6 py-2 text-base '

const toneClass = {
  alarm:
    'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200',
  quiet:
    'border-ui-border bg-ui-bg-secondary text-ui-text-secondary ' +
    'dark:border-ui-dark-border dark:bg-ui-dark-bg-secondary dark:text-ui-dark-text-secondary',
}

export function StatusBanner() {
  const client = useQueryClient()
  const { unreachable, lastSync } = useBackendStatus()
  const failures = useFailedActions()

  // What a cook can act on comes first: a tap that did not happen is theirs to retry, while
  // the connection is the app's problem to keep trying at.
  if (failures.length > 0) {
    const shown = failures.slice(0, MAX_SHOWN)
    return (
      <div role="alert" className={boxClass + toneClass.alarm}>
        {shown.map((failure) => (
          <span key={failure.id} className="flex items-center gap-2">
            <strong className="font-medium">{`${failure.label} failed`}</strong>
            <Button
              variant="secondary"
              size="sm"
              aria-label={`Retry ${failure.label}`}
              onClick={failure.retry}
            >
              Retry
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Dismiss ${failure.label}`}
              onClick={failure.dismiss}
            >
              ✕
            </Button>
          </span>
        ))}
        {failures.length > MAX_SHOWN && <span>{`and ${failures.length - MAX_SHOWN} more`}</span>}
      </div>
    )
  }

  if (unreachable) {
    return (
      <div role="alert" className={boxClass + toneClass.alarm}>
        <span>
          Not reaching the kitchen server
          {lastSync !== null && ` · showing stock from ${formatAgo(lastSync)}`}
        </span>
        <Button
          variant="secondary"
          size="sm"
          // Whatever failed, and whatever the open screen is watching: the failure may belong
          // to a page the cook has since walked away from, and it is the one to try again.
          onClick={() =>
            void client.refetchQueries({
              predicate: (query) => query.state.status === 'error' || query.isActive(),
            })
          }
        >
          Try again
        </Button>
      </div>
    )
  }

  // Nothing is failing, but nothing has landed for a while either: say so quietly rather than
  // let month-old stock read as this morning's.
  if (lastSync !== null && Date.now() - lastSync > STALE_AFTER_MS) {
    return (
      <div role="status" className={boxClass + toneClass.quiet}>
        <span>{`Last updated ${formatAgo(lastSync)}`}</span>
      </div>
    )
  }

  return null
}

export default StatusBanner
