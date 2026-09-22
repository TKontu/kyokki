/**
 * The consumption history, read back (H46), and kept fresh by the mutations that write it.
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { useBulkInventoryMove } from '../useInventory'
import { useConsumptionLog } from '../useConsumptionLog'
import type { ConsumptionLogEntry } from '@/types/consumption'

const entry = (overrides: Partial<ConsumptionLogEntry> = {}): ConsumptionLogEntry => ({
  id: 'l1',
  inventory_item_id: 'i1',
  product_master_id: 'p1',
  product_name: 'Milk',
  unit: 'dl',
  action: 'discard',
  quantity_consumed: 4,
  quantity_after: 0,
  logged_at: '2026-09-22T08:00:00+00:00',
  ...overrides,
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
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

describe('useConsumptionLog', () => {
  it('reads the waste back', async () => {
    let asked = ''
    server.use(
      http.get(`${API_URL}/consumption-log`, ({ request }) => {
        asked = new URL(request.url).search
        return HttpResponse.json([entry()])
      })
    )

    const { result } = renderHook(() => useConsumptionLog({ action: ['discard'] }), {
      wrapper: wrapper(newClient()),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([entry()])
    expect(asked).toBe('?action=discard')
  })

  it('renders an action this build has never heard of', async () => {
    server.use(
      http.get(`${API_URL}/consumption-log`, () =>
        HttpResponse.json([entry({ action: 'composted' })])
      )
    )

    const { result } = renderHook(() => useConsumptionLog(), {
      wrapper: wrapper(newClient()),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.[0].action).toBe('composted')
  })

  it('reads again after a clear, because the clear wrote to it', async () => {
    let reads = 0
    server.use(
      http.get(`${API_URL}/consumption-log`, () => {
        reads += 1
        return HttpResponse.json(reads === 1 ? [] : [entry()])
      }),
      http.get(`${API_URL}/inventory`, () => HttpResponse.json([])),
      http.post(`${API_URL}/inventory/discard`, () =>
        HttpResponse.json({ changed: [], refused: 0, missing: 0 })
      )
    )
    const client = newClient()
    const history = renderHook(() => useConsumptionLog(), { wrapper: wrapper(client) })
    const move = renderHook(() => useBulkInventoryMove(), { wrapper: wrapper(client) })
    await waitFor(() => expect(history.result.current.data).toEqual([]))

    await act(() => move.result.current.mutateAsync({ ids: ['i1'], event: 'discard' }))

    await waitFor(() => expect(history.result.current.data).toEqual([entry()]))
  })
})
