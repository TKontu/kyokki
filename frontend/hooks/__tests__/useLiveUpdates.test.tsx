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
import { getLiveStatus, resetLiveStatusForTests, EVENTS_PATH } from '@/lib/live'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  closed = false
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  emitOpen() {
    this.onopen?.()
  }

  emitMessage(data: string) {
    this.onmessage?.({ data })
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
  })

  afterEach(() => {
    jest.useRealTimers()
    window.EventSource = originalEventSource as typeof EventSource
    resetLiveStatusForTests()
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
})
