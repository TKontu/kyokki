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
 *
 * A dead connection does not always fire `onerror` - a half-open socket, or a
 * backgrounded home-screen PWA whose connection died silently, can just stop delivering
 * anything while `EventSource` still reports itself open. A staleness watchdog (F2)
 * tracks the time of the last byte received - any message, or the server's heartbeat,
 * which arrives as a named `ping` event rather than a plain SSE comment specifically so
 * this can see it - and forces a reconnect once that gets too old, rather than trusting
 * `onerror` alone.
 *
 * If connecting keeps failing without ever succeeding once, the live status becomes
 * `'failing'` after `FAILURE_THRESHOLD` attempts (F8): still retries forever at the
 * capped backoff (nothing here gives up), but `useInventory.ts` treats it the same as
 * `'disconnected'`, and it is worth one console warning so a persistent misconfiguration
 * (e.g. a token that is always rejected) is not completely silent.
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
/** The backend's heartbeat interval is 15 s (`HEARTBEAT_INTERVAL_SECONDS`,
 *  `backend/app/api/endpoints/events.py`). Three missed heartbeats, with no other
 *  message either, means the connection is dead even if it has not errored (F2). */
const STALE_AFTER_MS = 45_000
/** How often the watchdog checks for staleness while idle. */
const STALE_CHECK_INTERVAL_MS = 5_000
/** Connection attempts in a row with no successful open before `'failing'` (F8). */
const FAILURE_THRESHOLD = 5

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
    let staleCheckTimer: ReturnType<typeof setInterval> | null = null
    let backoff = INITIAL_BACKOFF_MS
    let everConnected = false
    let consecutiveFailures = 0
    let warnedAboutFailing = false
    let lastActivity = Date.now()
    let stopped = false

    const markAlive = () => {
      lastActivity = Date.now()
    }
    const isStale = () => Date.now() - lastActivity > STALE_AFTER_MS

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

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const scheduleReconnect = () => {
      if (stopped) return
      reconnectTimer = setTimeout(connect, backoff)
      backoff = nextBackoffMs(backoff)
    }

    const connect = () => {
      if (stopped || source) return
      clearReconnectTimer()
      // Not `lib/api/client.ts` (a fetch wrapper): EventSource is a browser API with its
      // own transport, not something a fetch wrapper can front. The token rule still
      // holds, because this is the same same-origin `/api` path every other request
      // uses - it passes through `middleware.ts` (token attached server-side) and the
      // Next.js rewrite exactly like a fetch to `/api/inventory` would (F6).
      const es = new EventSource(EVENTS_PATH)
      source = es
      markAlive()

      es.onopen = () => {
        if (source !== es) return
        backoff = INITIAL_BACKOFF_MS
        consecutiveFailures = 0
        warnedAboutFailing = false
        markAlive()
        setLiveStatus('connected')
        // A reconnect may have missed messages while the stream was down; a fresh first
        // connect has nothing to catch up on (the initial queries are already current).
        if (everConnected) invalidateAll()
        everConnected = true
      }
      es.onmessage = (event) => {
        if (source !== es) return
        markAlive()
        const message = parseLiveMessage(event.data)
        if (!message) return
        if (message.type === 'resync') {
          invalidateAll()
          return
        }
        keysForMessage(message).forEach(scheduleInvalidate)
      }
      // The heartbeat (`event: ping`, backend/app/api/endpoints/events.py) is a named
      // event rather than an SSE comment specifically so it reaches here: EventSource
      // never surfaces a bare `: comment` line to JavaScript at all.
      es.addEventListener('ping', () => {
        if (source !== es) return
        markAlive()
      })
      es.onerror = () => {
        if (source === es) source = null
        es.close()
        consecutiveFailures += 1
        if (consecutiveFailures >= FAILURE_THRESHOLD) {
          setLiveStatus('failing')
          if (!warnedAboutFailing) {
            warnedAboutFailing = true
            // The one deliberate console surface for F8 - no UI change, just a trail
            // for whoever is debugging why the iPad has gone quiet.
            // eslint-disable-next-line no-console
            console.warn(
              `useLiveUpdates: ${consecutiveFailures} connection attempts to ` +
                `${EVENTS_PATH} have failed in a row; still retrying at the capped backoff.`
            )
          }
        } else {
          setLiveStatus('disconnected')
        }
        scheduleReconnect()
      }
    }

    /** Used by both the periodic watchdog and a visibility/online check: closes a
     *  connection that is either gone or has gone silent, and reconnects at once. */
    const forceReconnect = () => {
      const dead = source
      if (dead) {
        source = null
        dead.close()
      }
      setLiveStatus('disconnected')
      connect()
    }

    const reconnectIfDown = () => {
      if (document.visibilityState === 'hidden') return
      if (!source || isStale()) forceReconnect()
    }

    staleCheckTimer = setInterval(() => {
      if (source && isStale()) forceReconnect()
    }, STALE_CHECK_INTERVAL_MS)

    connect()
    window.addEventListener('online', reconnectIfDown)
    document.addEventListener('visibilitychange', reconnectIfDown)

    return () => {
      stopped = true
      clearReconnectTimer()
      if (staleCheckTimer !== null) clearInterval(staleCheckTimer)
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
