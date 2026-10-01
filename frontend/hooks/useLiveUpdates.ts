/**
 * useLiveUpdates (A5)
 *
 * One SSE connection for the whole app, opened in `app/providers.tsx`: a change made
 * anywhere (another device, the Telegram bot, the agent CLI, the receipt worker) should
 * reach the iPad in about 2 seconds instead of waiting for the next poll.
 *
 * The browser never holds an API token (AG1), so it cannot open a WebSocket straight to
 * the backend. A plain `EventSource('/api/events')` is just another GET: it passes
 * through `middleware.ts` (which attaches the server-side token) and the Next.js rewrite
 * like any other request. See `backend/app/api/endpoints/events.py`.
 *
 * On a message, this invalidates the smallest set of TanStack Query keys the message
 * type implies, coalesced so a burst (a receipt confirm broadcasts many items) causes at
 * most one refetch per key rather than one per message. Polling remains the fallback:
 * `useInventory.ts` reads `lib/live.ts`'s connection status to relax its interval while
 * this is connected, and falls back to the normal 30 s poll the moment it is not.
 */

import { useEffect, useRef } from 'react'
import type { QueryClient, QueryKey } from '@tanstack/react-query'
import { inventoryKeys } from '@/hooks/useInventory'
import { receiptKeys } from '@/hooks/useReceipts'
import { productKeys } from '@/hooks/useProducts'
import { consumptionLogKeys } from '@/hooks/useConsumptionLog'
import {
  EVENTS_PATH,
  INITIAL_BACKOFF_MS,
  nextBackoffMs,
  parseLiveMessage,
  setLiveStatus,
  type LiveMessage,
} from '@/lib/live'

/** At most one invalidation per key within this window, however many messages land for it. */
const COALESCE_MS = 250

/** The smallest set of query keys a message type implies. Shopping has no frontend hook
 *  yet (it owns no query keys to invalidate), so `shopping_list_update` maps to none. */
function keysForMessage(message: LiveMessage): QueryKey[] {
  switch (message.type) {
    case 'inventory_update':
      return [inventoryKeys.lists(), consumptionLogKeys.all]
    case 'receipt_status': {
      const keys: QueryKey[] = [receiptKeys.all]
      // Only a confirm actually moves stock or can create a product; every other status
      // (uploaded/queued/processing/failed) only changes the receipt itself.
      if (message.data.status === 'confirmed') {
        keys.push(inventoryKeys.lists(), productKeys.all)
      }
      return keys
    }
    case 'product_update':
      return [productKeys.all, inventoryKeys.lists()]
    case 'scanner_action': {
      const keys: QueryKey[] = []
      if (message.data.mode === 'add' || message.data.mode === 'consume') {
        keys.push(inventoryKeys.lists())
      }
      if (message.data.action === 'product_created_and_added') {
        keys.push(productKeys.all)
      }
      return keys
    }
    default:
      return []
  }
}

/** Mounted once, in `Providers`. Takes the `QueryClient` as a parameter rather than reading
 *  it via `useQueryClient()` so it can run from the same component that constructs it. */
export function useLiveUpdates(queryClient: QueryClient): void {
  const pendingRef = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.EventSource === 'undefined') {
      return undefined
    }

    // Captured once per effect run, so the cleanup below clears the same map it scheduled
    // into, however `pendingRef.current` might look by the time the effect tears down.
    const pending = pendingRef.current

    let source: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let backoff = INITIAL_BACKOFF_MS
    let everConnected = false
    let stopped = false

    const invalidateAll = () => {
      queryClient.invalidateQueries()
    }

    const scheduleInvalidate = (key: QueryKey) => {
      const cacheKey = JSON.stringify(key)
      if (pending.has(cacheKey)) return
      const timeout = setTimeout(() => {
        pending.delete(cacheKey)
        queryClient.invalidateQueries({ queryKey: key })
      }, COALESCE_MS)
      pending.set(cacheKey, timeout)
    }

    const handleMessage = (event: MessageEvent<string>) => {
      const message = parseLiveMessage(event.data)
      if (!message) return
      if (message.type === 'resync') {
        invalidateAll()
        return
      }
      keysForMessage(message).forEach(scheduleInvalidate)
    }

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const connect = () => {
      if (stopped || source) return
      clearReconnectTimer()
      const es = new EventSource(EVENTS_PATH)
      source = es

      es.onopen = () => {
        backoff = INITIAL_BACKOFF_MS
        setLiveStatus('connected')
        // A reconnect may have missed messages while the stream was down; a fresh first
        // connect has nothing to catch up on (the initial queries are already current).
        if (everConnected) invalidateAll()
        everConnected = true
      }
      es.onmessage = handleMessage
      es.onerror = () => {
        setLiveStatus('disconnected')
        es.close()
        if (source === es) source = null
        if (stopped) return
        reconnectTimer = setTimeout(connect, backoff)
        backoff = nextBackoffMs(backoff)
      }
    }

    const reconnectIfDown = () => {
      if (document.visibilityState === 'hidden') return
      if (!source) connect()
    }

    connect()
    window.addEventListener('online', reconnectIfDown)
    document.addEventListener('visibilitychange', reconnectIfDown)

    return () => {
      stopped = true
      clearReconnectTimer()
      window.removeEventListener('online', reconnectIfDown)
      document.removeEventListener('visibilitychange', reconnectIfDown)
      source?.close()
      source = null
      setLiveStatus('disconnected')
      pending.forEach((timeout) => clearTimeout(timeout))
      pending.clear()
    }
  }, [queryClient])
}
