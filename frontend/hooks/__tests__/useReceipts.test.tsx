/**
 * Receipt queries poll while a receipt is being read and stop once it is finished (MVP-R5).
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { inventoryKeys } from '../useInventory'
import {
  detailPollInterval,
  IDLE_POLL_MS,
  listPollInterval,
  READING_POLL_MS,
  receiptKeys,
  useConfirmReceipt,
  useReceipt,
  useReceiptList,
} from '../useReceipts'
import type { Receipt } from '@/types/receipt'

const receipt = (overrides: Partial<Receipt> = {}) =>
  ({
    id: 'r1',
    processing_status: 'processing',
    items: [],
    items_extracted: 0,
    ...overrides,
  }) as Receipt

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  jest.useRealTimers()
})
afterAll(() => server.close())

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

const newClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

describe('poll intervals', () => {
  it.each(['queued', 'processing'] as const)('follows a receipt that is %s', (status) => {
    expect(detailPollInterval(receipt({ processing_status: status }))).toBe(READING_POLL_MS)
    expect(listPollInterval([receipt({ processing_status: status })])).toBe(READING_POLL_MS)
  })

  it.each(['completed', 'failed', 'confirmed'] as const)('stops once %s', (status) => {
    expect(detailPollInterval(receipt({ processing_status: status }))).toBe(false)
    expect(listPollInterval([receipt({ processing_status: status })])).toBe(IDLE_POLL_MS)
  })

  // A status this build does not know is not proof the worker is done with the receipt. Calling
  // it terminal stopped detail polling for good, so an unattended iPad sat on a stale page
  // forever; it now drops back to the idle heartbeat instead (H04).
  it.each(['uploaded', 'reprocessing', ''] as const)(
    'keeps a slow heartbeat on the unfinished status %p',
    (status) => {
      expect(detailPollInterval(receipt({ processing_status: status }))).toBe(IDLE_POLL_MS)
      expect(listPollInterval([receipt({ processing_status: status })])).toBe(IDLE_POLL_MS)
    }
  )

  it('has nothing to follow before the first load', () => {
    expect(detailPollInterval(undefined)).toBe(false)
    expect(listPollInterval(undefined)).toBe(IDLE_POLL_MS)
  })
})

describe('useReceipt', () => {
  it('loads the receipt and stops fetching once it is finished', async () => {
    let calls = 0
    server.use(
      http.get(`${API_URL}/receipts/r1`, () => {
        calls += 1
        return HttpResponse.json(receipt({ processing_status: 'completed' }))
      })
    )
    const { result } = renderHook(() => useReceipt('r1'), { wrapper: wrapper(newClient()) })

    await waitFor(() => expect(result.current.data?.processing_status).toBe('completed'))
    expect(calls).toBe(1)
  })

  it('does not query without an id', () => {
    // Fake timers, not a 200 ms sleep: the assertion is that nothing happened, so there is no
    // network to wait for and a real wait only bought flakiness on a loaded machine (H06).
    jest.useFakeTimers()
    const seen: string[] = []
    server.use(
      http.get(`${API_URL}/receipts/:id`, ({ params }) => {
        seen.push(String(params.id))
        return HttpResponse.json(receipt())
      })
    )
    renderHook(() => useReceipt(''), { wrapper: wrapper(newClient()) })

    act(() => {
      jest.advanceTimersByTime(READING_POLL_MS)
    })
    expect(seen).toEqual([])
  })
})

describe('useReceiptList', () => {
  it('loads receipts', async () => {
    server.use(http.get(`${API_URL}/receipts`, () => HttpResponse.json([receipt()])))
    const { result } = renderHook(() => useReceiptList(), { wrapper: wrapper(newClient()) })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
  })
})

describe('useConfirmReceipt', () => {
  const request = {
    items: [{ index: 0, name: 'Milk', category: 'dairy', quantity: 1, unit: 'pcs', purchase_date: '2026-09-02' }],
  }

  it('posts once and refreshes inventory, receipts and products', async () => {
    let posts = 0
    server.use(
      http.post(`${API_URL}/receipts/r1/confirm`, () => {
        posts += 1
        return HttpResponse.json({
          success: true,
          items_created: 1,
          products_created: 1,
          aliases_learned: 1,
          error: null,
        })
      })
    )
    const queryClient = newClient()
    const invalidate = jest.spyOn(queryClient, 'invalidateQueries')
    const { result } = renderHook(() => useConfirmReceipt(), { wrapper: wrapper(queryClient) })

    await act(async () => {
      await result.current.mutateAsync({ id: 'r1', data: request })
    })

    expect(posts).toBe(1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: inventoryKeys.lists() })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: receiptKeys.all })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['products'] })
  })

  it('never retries: confirming twice would double the stock', async () => {
    let posts = 0
    server.use(
      http.post(`${API_URL}/receipts/r1/confirm`, () => {
        posts += 1
        return HttpResponse.json({ detail: 'boom' }, { status: 500 })
      })
    )
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: 1 } } })
    const { result } = renderHook(() => useConfirmReceipt(), { wrapper: wrapper(queryClient) })

    await act(async () => {
      await result.current.mutateAsync({ id: 'r1', data: request }).catch(() => {})
    })

    expect(posts).toBe(1)
  })
})
