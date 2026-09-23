'use client'

/**
 * useBackendStatus (H45)
 *
 * The iPad runs unattended, so a screen that cannot reach the kitchen server must say so
 * rather than show month-old stock as if it were fresh. This derives that from the queries the
 * open page already runs - no polling of its own, and nothing to keep in sync.
 */

import { useEffect, useState } from 'react'
import { onlineManager, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { isAPIError, isNetworkError } from '@/lib/api/errors'

/** Re-read the clock this often, so "4 minutes ago" keeps counting without a render storm. */
export const TICK_MS = 15_000

/**
 * Old enough to be worth saying. Three times the stock poll (`INVENTORY_POLL_MS`), so one slow
 * or dropped request says nothing and a display that has genuinely stopped updating does.
 */
export const STALE_AFTER_MS = 90_000

export interface BackendStatus {
  /** The kitchen server is not answering, or this tablet is off the network. */
  unreachable: boolean
  /** When anything last landed, or null if nothing has yet. */
  lastSync: number | null
}

/**
 * A failure that says something about the connection rather than about one request.
 *
 * A 404 on a receipt somebody deleted is not a network problem, and banners that cry wolf get
 * ignored. A 5xx is: the server is reachable and cannot do its job, which on a wall display
 * means the same thing to the cook.
 */
function meansOutOfTouch(error: unknown): boolean {
  if (isNetworkError(error)) return true
  return isAPIError(error) && error.status >= 500
}

function read(client: QueryClient): BackendStatus {
  const queries = client.getQueryCache().getAll()
  let lastSync: number | null = null
  let unreachable = !onlineManager.isOnline()

  for (const query of queries) {
    const { dataUpdatedAt, status, error } = query.state
    if (status === 'success' && dataUpdatedAt > 0) {
      lastSync = Math.max(lastSync ?? 0, dataUpdatedAt)
    }
    if (status === 'error' && meansOutOfTouch(error)) {
      unreachable = true
    }
  }

  return { unreachable, lastSync }
}

export function useBackendStatus(): BackendStatus {
  const client = useQueryClient()
  const [status, setStatus] = useState<BackendStatus>(() => read(client))

  useEffect(() => {
    const refresh = () => setStatus(read(client))
    refresh()
    const unsubscribeCache = client.getQueryCache().subscribe(refresh)
    const unsubscribeOnline = onlineManager.subscribe(refresh)
    const ticker = setInterval(refresh, TICK_MS)
    return () => {
      unsubscribeCache()
      unsubscribeOnline()
      clearInterval(ticker)
    }
  }, [client])

  return status
}
