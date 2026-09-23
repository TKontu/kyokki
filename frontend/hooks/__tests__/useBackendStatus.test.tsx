/**
 * The wall iPad has to admit when it is out of touch (H45). This is where that is decided:
 * what is on screen, how old it is, and whether the kitchen server is answering at all.
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useBackendStatus } from '../useBackendStatus'
import { APIError, NetworkError } from '@/lib/api/errors'

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

const newClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false } } })

afterEach(() => onlineManager.setOnline(true))

/** A query that succeeded, as the open page's poll would leave it. */
async function succeed(client: QueryClient, key: string, at?: number) {
  await client.fetchQuery({ queryKey: [key], queryFn: async () => 'ok' })
  if (at !== undefined) {
    const query = client.getQueryCache().find({ queryKey: [key] })
    query!.setState({ ...query!.state, dataUpdatedAt: at })
  }
}

async function fail(client: QueryClient, key: string, error: Error) {
  await client
    .fetchQuery({
      queryKey: [key],
      queryFn: async () => {
        throw error
      },
    })
    .catch(() => undefined)
}

describe('useBackendStatus', () => {
  it('says nothing is wrong when the polls are landing', async () => {
    const client = newClient()
    await succeed(client, 'inventory')

    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(client) })

    expect(result.current.unreachable).toBe(false)
    expect(result.current.lastSync).toBeGreaterThan(0)
  })

  it('has no last sync before anything has landed', () => {
    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(newClient()) })

    expect(result.current.lastSync).toBeNull()
  })

  it('follows the newest thing that landed', async () => {
    const client = newClient()
    await succeed(client, 'older', 1000)
    await succeed(client, 'newer', 5000)

    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(client) })

    expect(result.current.lastSync).toBe(5000)
  })

  it('is unreachable when a request cannot get out, and keeps the old sync time', async () => {
    const client = newClient()
    await succeed(client, 'inventory', 1000)

    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(client) })
    await act(async () => {
      await fail(client, 'receipts', new NetworkError('Network request failed'))
    })

    await waitFor(() => expect(result.current.unreachable).toBe(true))
    // The stock on screen is still the stock that landed at 1000; the banner says how old it is
    expect(result.current.lastSync).toBe(1000)
  })

  it('is unreachable when the server answers but cannot do its job', async () => {
    const client = newClient()

    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(client) })
    await act(async () => {
      await fail(client, 'inventory', new APIError(503, 'UNAVAILABLE', 'Service Unavailable'))
    })

    await waitFor(() => expect(result.current.unreachable).toBe(true))
  })

  it('is not unreachable over one missing thing', async () => {
    // A 404 on a receipt somebody deleted says nothing about the connection.
    const client = newClient()

    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(client) })
    await act(async () => {
      await fail(client, 'receipt', new APIError(404, 'NOT_FOUND', 'No such receipt'))
    })

    expect(result.current.unreachable).toBe(false)
  })

  it('is unreachable while the tablet itself is offline', async () => {
    const client = newClient()
    await succeed(client, 'inventory')
    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(client) })

    act(() => onlineManager.setOnline(false))

    await waitFor(() => expect(result.current.unreachable).toBe(true))
  })

  it('recovers when a request lands again', async () => {
    const client = newClient()
    const { result } = renderHook(() => useBackendStatus(), { wrapper: wrapper(client) })
    await act(async () => {
      await fail(client, 'inventory', new NetworkError('Network request failed'))
    })
    await waitFor(() => expect(result.current.unreachable).toBe(true))

    await act(async () => {
      await succeed(client, 'inventory')
    })

    await waitFor(() => expect(result.current.unreachable).toBe(false))
  })
})
