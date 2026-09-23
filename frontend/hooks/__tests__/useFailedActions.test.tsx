/**
 * A failed action must survive being missed (H45): card taps raise no success toast, and an
 * error toast is gone in five seconds on a display nobody is watching.
 */

import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useFailedActions } from '../useFailedActions'

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

const newClient = () =>
  new QueryClient({ defaultOptions: { mutations: { retry: false } } })

/** Run a mutation the way a hook would, so the cache sees it fail. */
async function run(
  client: QueryClient,
  mutationFn: (variables: unknown) => Promise<unknown>,
  { label, variables }: { label?: string; variables?: unknown } = {}
) {
  const mutation = client.getMutationCache().build(client, {
    mutationFn: mutationFn as never,
    meta: label ? { label } : undefined,
    retry: false,
  })
  await mutation.execute(variables as never).catch(() => undefined)
  return mutation
}

describe('useFailedActions', () => {
  it('has nothing to show while everything works', async () => {
    const client = newClient()
    const { result } = renderHook(() => useFailedActions(), { wrapper: wrapper(client) })

    await act(async () => {
      await run(client, async () => 'fine', { label: 'Consume' })
    })

    expect(result.current).toEqual([])
  })

  it('remembers a failed action by what it was', async () => {
    const client = newClient()
    const { result } = renderHook(() => useFailedActions(), { wrapper: wrapper(client) })

    await act(async () => {
      await run(client, async () => Promise.reject(new Error('nope')), { label: 'Consume' })
    })

    await waitFor(() => expect(result.current).toHaveLength(1))
    expect(result.current[0].label).toBe('Consume')
    expect(result.current[0].failedAt).toBeGreaterThan(0)
  })

  it('names an action that did not say what it was', async () => {
    const client = newClient()
    const { result } = renderHook(() => useFailedActions(), { wrapper: wrapper(client) })

    await act(async () => {
      await run(client, async () => Promise.reject(new Error('nope')))
    })

    await waitFor(() => expect(result.current[0].label).toBe('An action'))
  })

  it('newest first, so the last thing tapped is the first thing offered', async () => {
    const client = newClient()
    const { result } = renderHook(() => useFailedActions(), { wrapper: wrapper(client) })

    await act(async () => {
      await run(client, async () => Promise.reject(new Error('nope')), { label: 'Consume' })
      await run(client, async () => Promise.reject(new Error('nope')), { label: 'Save' })
    })

    await waitFor(() => expect(result.current).toHaveLength(2))
    expect(result.current.map((each) => each.label)).toEqual(['Save', 'Consume'])
  })

  it('retries the same request, with what it was given the first time', async () => {
    const client = newClient()
    const seen: unknown[] = []
    let fail = true
    const mutationFn = async (variables: unknown) => {
      seen.push(variables)
      if (fail) throw new Error('nope')
      return 'ok'
    }
    const { result } = renderHook(() => useFailedActions(), { wrapper: wrapper(client) })
    await act(async () => {
      await run(client, mutationFn, { label: 'Consume', variables: { id: 'i1', amount: 250 } })
    })
    await waitFor(() => expect(result.current).toHaveLength(1))

    fail = false
    await act(async () => {
      result.current[0].retry()
    })

    await waitFor(() => expect(result.current).toEqual([]))
    expect(seen).toEqual([
      { id: 'i1', amount: 250 },
      { id: 'i1', amount: 250 },
    ])
  })

  it('keeps the row when the retry fails too', async () => {
    const client = newClient()
    const { result } = renderHook(() => useFailedActions(), { wrapper: wrapper(client) })
    await act(async () => {
      await run(client, async () => Promise.reject(new Error('nope')), { label: 'Consume' })
    })
    await waitFor(() => expect(result.current).toHaveLength(1))

    await act(async () => {
      result.current[0].retry()
    })

    await waitFor(() => expect(result.current).toHaveLength(1))
  })

  it('can be waved away by hand', async () => {
    const client = newClient()
    const { result } = renderHook(() => useFailedActions(), { wrapper: wrapper(client) })
    await act(async () => {
      await run(client, async () => Promise.reject(new Error('nope')), { label: 'Consume' })
    })
    await waitFor(() => expect(result.current).toHaveLength(1))

    act(() => result.current[0].dismiss())

    await waitFor(() => expect(result.current).toEqual([]))
  })
})
