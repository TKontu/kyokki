/**
 * The non-React pieces of the live-updates stream (A5): message parsing, backoff and the
 * connection-status store `useLiveUpdates.ts` and `useInventory.ts` share.
 */

import {
  EVENTS_PATH,
  INITIAL_BACKOFF_MS,
  MAX_BACKOFF_MS,
  getLiveStatus,
  nextBackoffMs,
  parseLiveMessage,
  resetLiveStatusForTests,
  setLiveStatus,
  subscribeLiveStatus,
} from '../live'

describe('parseLiveMessage', () => {
  it('parses a well-formed broadcast message', () => {
    const raw = JSON.stringify({
      type: 'inventory_update',
      timestamp: '2026-10-01T00:00:00+00:00',
      entity_id: '11111111-1111-1111-1111-111111111111',
      data: { action: 'created' },
    })

    expect(parseLiveMessage(raw)).toEqual({
      type: 'inventory_update',
      timestamp: '2026-10-01T00:00:00+00:00',
      entity_id: '11111111-1111-1111-1111-111111111111',
      data: { action: 'created' },
    })
  })

  it('returns null for malformed JSON', () => {
    expect(parseLiveMessage('not json')).toBeNull()
  })

  it('returns null for JSON with no string type', () => {
    expect(parseLiveMessage(JSON.stringify({ data: {} }))).toBeNull()
    expect(parseLiveMessage(JSON.stringify({ type: 42 }))).toBeNull()
    expect(parseLiveMessage('null')).toBeNull()
    expect(parseLiveMessage('"a string"')).toBeNull()
  })
})

describe('nextBackoffMs', () => {
  it('doubles', () => {
    expect(nextBackoffMs(1_000)).toBe(2_000)
    expect(nextBackoffMs(2_000)).toBe(4_000)
  })

  it('caps at MAX_BACKOFF_MS', () => {
    expect(nextBackoffMs(MAX_BACKOFF_MS)).toBe(MAX_BACKOFF_MS)
    expect(nextBackoffMs(MAX_BACKOFF_MS * 10)).toBe(MAX_BACKOFF_MS)
  })

  it('starts below the cap', () => {
    expect(INITIAL_BACKOFF_MS).toBeLessThan(MAX_BACKOFF_MS)
  })
})

describe('live status store', () => {
  afterEach(() => resetLiveStatusForTests())

  it('starts disconnected', () => {
    expect(getLiveStatus()).toBe('disconnected')
  })

  it('notifies subscribers only on an actual change', () => {
    const listener = jest.fn()
    const unsubscribe = subscribeLiveStatus(listener)

    setLiveStatus('disconnected') // already disconnected: no-op
    expect(listener).not.toHaveBeenCalled()

    setLiveStatus('connected')
    expect(listener).toHaveBeenCalledTimes(1)
    expect(getLiveStatus()).toBe('connected')

    setLiveStatus('connected') // unchanged: no-op
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    setLiveStatus('disconnected')
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('EVENTS_PATH', () => {
  it('is a same-origin relative path, so it goes through middleware.ts and the rewrite', () => {
    expect(EVENTS_PATH).toBe('/api/events')
  })
})
