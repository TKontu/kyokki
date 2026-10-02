/**
 * useLiveUpdates (A5): one SSE connection, invalidating the right query keys as broadcasts
 * arrive, reconnecting with backoff, and resyncing everything on a reconnect or a `resync`
 * event. jsdom has no real `EventSource`, so these tests drive a small fake one instead.
 */

import { renderHook, act } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import { useLiveUpdates } from '../useLiveUpdates'
import { inventoryKeys } from '../useInventory'
import { receiptKeys } from '../useReceipts'
import { productKeys } from '../useProducts'
import { consumptionLogKeys } from '../useConsumptionLog'
import { shoppingKeys } from '../useShopping'
import { getLiveStatus, resetLiveStatusForTests, EVENTS_PATH } from '@/lib/live'

/** F5: models everything the hook relies on, including "open, then silent" - which
 *  needs no special support here, since the fake only ever reacts to an `emit*` call: a
 *  test that opens a connection and then simply stops calling `emit*` while advancing
 *  fake timers *is* a connection that looks alive but has gone quiet. */
class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  private listeners = new Map<string, Set<(event: { data: string }) => void>>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  addEventListener(type: string, handler: (event: { data: string }) => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set())
    this.listeners.get(type)?.add(handler)
  }

  removeEventListener(type: string, handler: (event: { data: string }) => void) {
    this.listeners.get(type)?.delete(handler)
  }

  emitOpen() {
    this.onopen?.()
  }

  emitMessage(data: string) {
    this.onmessage?.({ data })
  }

  /** The named heartbeat event (`event: ping`), not a bare SSE comment - see F2. */
  emitPing() {
    this.listeners.get('ping')?.forEach((handler) => handler({ data: '' }))
  }

  emitError() {
    this.onerror?.()
  }
}

function latestSource(): FakeEventSource {
  const instance = FakeEventSource.instances[FakeEventSource.instances.length - 1]
  if (!instance) throw new Error('no EventSource was constructed')
  return instance
}

function message(type: string, data: Record<string, unknown> = {}) {
  return JSON.stringify({
    type,
    timestamp: '2026-10-01T00:00:00+00:00',
    entity_id: '11111111-1111-1111-1111-111111111111',
    data,
  })
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('useLiveUpdates', () => {
  let originalEventSource: typeof window.EventSource | undefined

  beforeEach(() => {
    originalEventSource = window.EventSource
    FakeEventSource.instances = []
    window.EventSource = FakeEventSource as unknown as typeof EventSource
    jest.useFakeTimers()
    // F8's one console surface is expected in a couple of tests here, and incidental in
    // others (enough errors in a row crosses the threshold); keep every test's output
    // clean rather than asserting silence everywhere.
    jest.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    jest.useRealTimers()
    window.EventSource = originalEventSource as typeof EventSource
    resetLiveStatusForTests()
    jest.restoreAllMocks()
  })

  it('opens exactly one connection, at /api/events', () => {
    renderHook(() => useLiveUpdates(newClient()))
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toBe(EVENTS_PATH)
  })

  it('does nothing when EventSource is not available (SSR / no polyfill)', () => {
    window.EventSource = undefined as unknown as typeof EventSource
    expect(() => renderHook(() => useLiveUpdates(newClient()))).not.toThrow()
    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('marks the stream connected on open, disconnected on error', () => {
    renderHook(() => useLiveUpdates(newClient()))
    expect(getLiveStatus()).toBe('disconnected')

    act(() => latestSource().emitOpen())
    expect(getLiveStatus()).toBe('connected')

    act(() => latestSource().emitError())
    expect(getLiveStatus()).toBe('disconnected')
  })

  it('invalidates the smallest key set for an inventory_update', () => {
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    renderHook(() => useLiveUpdates(queryClient))

    act(() => {
      latestSource().emitMessage(message('inventory_update', { action: 'created' }))
      jest.advanceTimersByTime(300)
    })

    expect(invalidate).toHaveBeenCalledWith({ queryKey: inventoryKeys.lists() })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: consumptionLogKeys.all })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: receiptKeys.all })
  })

  it('only invalidates inventory/products for a confirmed receipt, not an in-progress one', () => {
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    renderHook(() => useLiveUpdates(queryClient))

    act(() => {
      latestSource().emitMessage(message('receipt_status', { status: 'processing' }))
      jest.advanceTimersByTime(300)
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: receiptKeys.all })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: inventoryKeys.lists() })

    invalidate.mockClear()
    act(() => {
      latestSource().emitMessage(message('receipt_status', { status: 'confirmed' }))
      jest.advanceTimersByTime(300)
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: receiptKeys.all })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: inventoryKeys.lists() })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: productKeys.all })
  })

  it('coalesces a burst into one refetch per key, not one per message', () => {
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    renderHook(() => useLiveUpdates(queryClient))

    act(() => {
      const source = latestSource()
      // A 15-line receipt confirm broadcasts many inventory_update messages.
      for (let i = 0; i < 15; i += 1) {
        source.emitMessage(message('inventory_update', { action: 'created' }))
      }
      jest.advanceTimersByTime(300)
    })

    const inventoryCalls = invalidate.mock.calls.filter(
      ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(inventoryKeys.lists())
    )
    expect(inventoryCalls).toHaveLength(1)
  })

  it('invalidates shoppingKeys.all once per burst for shopping_list_update, and leaves inventory alone', () => {
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    renderHook(() => useLiveUpdates(queryClient))

    act(() => {
      const source = latestSource()
      for (let i = 0; i < 15; i += 1) {
        source.emitMessage(message('shopping_list_update', { action: 'purchased' }))
      }
      jest.advanceTimersByTime(300)
    })

    const shoppingCalls = invalidate.mock.calls.filter(
      ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(shoppingKeys.all)
    )
    expect(shoppingCalls).toHaveLength(1)
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: inventoryKeys.lists() })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: consumptionLogKeys.all })
  })

  it('invalidates everything once on a resync event', () => {
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    renderHook(() => useLiveUpdates(queryClient))

    act(() => {
      latestSource().emitMessage(message('resync'))
    })

    expect(invalidate).toHaveBeenCalledWith()
  })

  it('invalidates everything once on a reconnect, not on the first connect', () => {
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    renderHook(() => useLiveUpdates(queryClient))

    act(() => latestSource().emitOpen())
    expect(invalidate).not.toHaveBeenCalled()

    act(() => {
      latestSource().emitError()
      jest.advanceTimersByTime(5_000)
    })
    act(() => latestSource().emitOpen())
    expect(invalidate).toHaveBeenCalledWith()
  })

  it('reconnects with doubling backoff, capped at 30s', () => {
    renderHook(() => useLiveUpdates(newClient()))

    act(() => latestSource().emitError())
    expect(FakeEventSource.instances).toHaveLength(1)
    act(() => jest.advanceTimersByTime(999))
    expect(FakeEventSource.instances).toHaveLength(1) // not yet - under 1s
    act(() => jest.advanceTimersByTime(1))
    expect(FakeEventSource.instances).toHaveLength(2) // 1s backoff elapsed

    act(() => latestSource().emitError())
    act(() => jest.advanceTimersByTime(1_999))
    expect(FakeEventSource.instances).toHaveLength(2)
    act(() => jest.advanceTimersByTime(1))
    expect(FakeEventSource.instances).toHaveLength(3) // 2s backoff elapsed

    // Keep failing; the delay must never exceed 30s between attempts.
    for (let i = 0; i < 6; i += 1) {
      act(() => latestSource().emitError())
      act(() => jest.advanceTimersByTime(30_000))
    }
    expect(FakeEventSource.instances.length).toBeGreaterThan(3)
  })

  it('reconnects right away on "online" while disconnected, without waiting out the backoff', () => {
    renderHook(() => useLiveUpdates(newClient()))
    act(() => latestSource().emitError())
    expect(FakeEventSource.instances).toHaveLength(1)

    act(() => window.dispatchEvent(new Event('online')))
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('reconnects on visibilitychange while visible, not while hidden', () => {
    renderHook(() => useLiveUpdates(newClient()))
    act(() => latestSource().emitError())
    expect(FakeEventSource.instances).toHaveLength(1)

    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      configurable: true,
    })
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(FakeEventSource.instances).toHaveLength(1)

    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      configurable: true,
    })
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('does not open a second connection while already connected', () => {
    renderHook(() => useLiveUpdates(newClient()))
    act(() => latestSource().emitOpen())
    act(() => window.dispatchEvent(new Event('online')))
    expect(FakeEventSource.instances).toHaveLength(1)
  })

  it('cleans up on unmount: closes the stream, drops pending invalidations, goes disconnected', () => {
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    const { unmount } = renderHook(() => useLiveUpdates(queryClient))

    act(() => latestSource().emitOpen())
    const source = latestSource()
    act(() => {
      source.emitMessage(message('inventory_update'))
    })

    unmount()

    expect(source.closed).toBe(true)
    expect(getLiveStatus()).toBe('disconnected')

    invalidate.mockClear()
    act(() => jest.advanceTimersByTime(1_000))
    expect(invalidate).not.toHaveBeenCalled()
  })

  describe('the staleness watchdog (F2)', () => {
    it('reconnects a connection that looks open but has gone silent for 3 missed heartbeats', () => {
      renderHook(() => useLiveUpdates(newClient()))
      act(() => latestSource().emitOpen())
      expect(getLiveStatus()).toBe('connected')

      // Just under 45s (3 x the backend's 15s heartbeat): still trusted.
      act(() => jest.advanceTimersByTime(49_999))
      expect(FakeEventSource.instances).toHaveLength(1)
      expect(getLiveStatus()).toBe('connected')

      // The next 5s watchdog tick crosses 45s of total silence.
      act(() => jest.advanceTimersByTime(1))
      expect(FakeEventSource.instances).toHaveLength(2)
      expect(FakeEventSource.instances[0].closed).toBe(true)
      expect(getLiveStatus()).toBe('disconnected')
    })

    it('a heartbeat (the named "ping" event) keeps the connection from going stale', () => {
      renderHook(() => useLiveUpdates(newClient()))
      act(() => latestSource().emitOpen())

      // Four 20s steps (80s total) comfortably exceed the 45s staleness window, but each
      // step is under it individually, and a ping resets the clock every time.
      for (let i = 0; i < 4; i += 1) {
        act(() => {
          jest.advanceTimersByTime(20_000)
          latestSource().emitPing()
        })
      }

      expect(FakeEventSource.instances).toHaveLength(1)
      expect(getLiveStatus()).toBe('connected')
    })

    it('an ordinary message also counts as activity, not only open/ping', () => {
      renderHook(() => useLiveUpdates(newClient()))
      act(() => latestSource().emitOpen())

      for (let i = 0; i < 4; i += 1) {
        act(() => {
          jest.advanceTimersByTime(20_000)
          latestSource().emitMessage(message('inventory_update'))
        })
      }

      expect(FakeEventSource.instances).toHaveLength(1)
      expect(getLiveStatus()).toBe('connected')
    })

    it('treats a stale source as down on visibilitychange, not only a null one', () => {
      Object.defineProperty(document, 'visibilityState', {
        value: 'visible',
        configurable: true,
      })
      renderHook(() => useLiveUpdates(newClient()))
      act(() => latestSource().emitOpen())
      expect(FakeEventSource.instances).toHaveLength(1)

      // Jump the clock without advancing fake timers, so the periodic watchdog's own
      // interval does not fire first - this isolates the visibilitychange handler's own
      // staleness check, the thing this test is actually about.
      jest.spyOn(Date, 'now').mockReturnValue(Date.now() + 46_000)

      act(() => document.dispatchEvent(new Event('visibilitychange')))
      expect(FakeEventSource.instances).toHaveLength(2)
      expect(FakeEventSource.instances[0].closed).toBe(true)
    })

    it('treats a stale source as down on "online" too', () => {
      renderHook(() => useLiveUpdates(newClient()))
      act(() => latestSource().emitOpen())
      expect(FakeEventSource.instances).toHaveLength(1)

      jest.spyOn(Date, 'now').mockReturnValue(Date.now() + 46_000)

      act(() => window.dispatchEvent(new Event('online')))
      expect(FakeEventSource.instances).toHaveLength(2)
      expect(FakeEventSource.instances[0].closed).toBe(true)
    })
  })

  describe('stale-instance guards (F7)', () => {
    it('ignores onopen/onmessage from an instance that is no longer the live source', () => {
      const queryClient = newClient()
      const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
      renderHook(() => useLiveUpdates(queryClient))

      const first = latestSource()
      act(() => {
        first.emitError()
        jest.advanceTimersByTime(1_000) // the scheduled reconnect fires
      })
      expect(FakeEventSource.instances).toHaveLength(2)
      const second = latestSource()
      act(() => second.emitOpen())
      expect(getLiveStatus()).toBe('connected')

      invalidate.mockClear()
      // The old, already-replaced instance firing late (a real EventSource should not
      // do this once closed, but nothing stops a queued microtask) must be a no-op.
      act(() => {
        first.emitOpen()
        first.emitMessage(message('inventory_update'))
        jest.advanceTimersByTime(300)
      })
      expect(invalidate).not.toHaveBeenCalled()
      expect(getLiveStatus()).toBe('connected')
    })
  })

  describe('a "failing" status for a connection that never succeeds (F8)', () => {
    it('surfaces "failing" and warns once after FAILURE_THRESHOLD failures with no open', () => {
      renderHook(() => useLiveUpdates(newClient()))
      const warn = console.warn as jest.Mock

      // Four failures in a row: still just "disconnected", no warning yet.
      for (let i = 0; i < 4; i += 1) {
        act(() => {
          latestSource().emitError()
          jest.advanceTimersByTime(30_000) // comfortably past that attempt's backoff
        })
      }
      expect(getLiveStatus()).toBe('disconnected')
      expect(warn).not.toHaveBeenCalled()

      // The 5th failure in a row crosses the threshold.
      act(() => latestSource().emitError())
      expect(getLiveStatus()).toBe('failing')
      expect(warn).toHaveBeenCalledTimes(1)

      // It keeps retrying at the capped backoff, but does not warn again.
      act(() => jest.advanceTimersByTime(30_000))
      act(() => latestSource().emitError())
      expect(getLiveStatus()).toBe('failing')
      expect(warn).toHaveBeenCalledTimes(1)
    })

    it('a successful open resets the failure count and leaves the status connected', () => {
      renderHook(() => useLiveUpdates(newClient()))
      const warn = console.warn as jest.Mock

      for (let i = 0; i < 4; i += 1) {
        act(() => {
          latestSource().emitError()
          jest.advanceTimersByTime(30_000)
        })
      }
      act(() => latestSource().emitOpen())
      expect(getLiveStatus()).toBe('connected')

      // Erroring again afterwards starts counting from zero, not from 4.
      act(() => latestSource().emitError())
      expect(getLiveStatus()).toBe('disconnected')
      expect(warn).not.toHaveBeenCalled()
    })
  })
})
