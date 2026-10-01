/**
 * Shared, non-React pieces of the live-updates stream (A5): the message shape that mirrors
 * the backend's broadcast (`backend/app/services/broadcast_helpers.py` via
 * `GET /api/events`, `backend/app/api/endpoints/events.py`), the reconnect backoff schedule,
 * and a small store other hooks read to know whether the stream is currently connected.
 *
 * `useInventory.ts` reads `getLiveStatus`/`subscribeLiveStatus` to relax its poll interval
 * while the stream is carrying updates. The connection itself lives in `useLiveUpdates.ts`,
 * which is the only thing that calls `setLiveStatus`.
 */

/** Same origin as every other `/api/*` call, so it passes through `middleware.ts` and the
 *  Next.js rewrite like any GET — the token never has to reach the browser (AG1). */
export const EVENTS_PATH = '/api/events'

/** Delay before the first reconnect attempt, and the step a repeated failure doubles from. */
export const INITIAL_BACKOFF_MS = 1_000
/** Delay never grows past this. */
export const MAX_BACKOFF_MS = 30_000

/** Exponential backoff, capped. */
export function nextBackoffMs(current: number): number {
  return Math.min(current * 2, MAX_BACKOFF_MS)
}

/** The shape every broadcast message has (`_build_message` in `broadcast_helpers.py`), plus
 *  the synthetic `resync` event a client gets in place of one it fell too far behind to receive. */
export interface LiveMessage {
  type: string
  timestamp: string
  entity_id: string | null
  data: Record<string, unknown>
}

/** Parses one SSE `data:` payload. `null` for anything that is not a JSON object with a `type`
 *  (defensive only — the backend never sends anything else on this channel). */
export function parseLiveMessage(raw: string): LiveMessage | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (
    parsed !== null &&
    typeof parsed === 'object' &&
    typeof (parsed as Record<string, unknown>).type === 'string'
  ) {
    return parsed as LiveMessage
  }
  return null
}

/** `'failing'` (F8): connecting has failed `FAILURE_THRESHOLD` times in a row without
 *  ever succeeding once. Every reader that only cares about "is it carrying updates
 *  right now" (e.g. `useInventory.ts`'s poll interval) should treat it exactly like
 *  `'disconnected'` - it exists only so something can be surfaced for a connection that
 *  is not just briefly down but stuck. */
export type LiveStatus = 'connected' | 'disconnected' | 'failing'

let liveStatus: LiveStatus = 'disconnected'
const listeners = new Set<() => void>()

/** The stream's current status. Starts (and falls back to) `'disconnected'`, which is what
 *  every reader wants when the stream has never connected — the existing 30 s poll. */
export function getLiveStatus(): LiveStatus {
  return liveStatus
}

/** Only `useLiveUpdates.ts` calls this. */
export function setLiveStatus(status: LiveStatus): void {
  if (status === liveStatus) return
  liveStatus = status
  listeners.forEach((listener) => listener())
}

export function subscribeLiveStatus(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Test-only: put the module-level status back to its starting point between tests. */
export function resetLiveStatusForTests(): void {
  liveStatus = 'disconnected'
}
