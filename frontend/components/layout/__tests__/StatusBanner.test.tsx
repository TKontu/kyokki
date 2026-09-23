/**
 * The one line that tells an unattended display the truth (H45): that it cannot reach the
 * kitchen server, that what it shows is old, or that something a cook tapped did not happen.
 * Silent otherwise - a banner that is always there is a banner nobody reads.
 */

import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StatusBanner } from '../StatusBanner'
import { NetworkError } from '@/lib/api/errors'
import { STALE_AFTER_MS } from '@/hooks/useBackendStatus'

const newClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

function renderBanner(client: QueryClient) {
  render(
    <QueryClientProvider client={client}>
      <StatusBanner />
    </QueryClientProvider>
  )
}

async function landed(client: QueryClient, key = 'inventory', at?: number) {
  await client.fetchQuery({ queryKey: [key], queryFn: async () => 'ok' })
  if (at !== undefined) {
    const query = client.getQueryCache().find({ queryKey: [key] })!
    query.setState({ ...query.state, dataUpdatedAt: at })
  }
}

async function failed(client: QueryClient, key = 'inventory') {
  await client
    .fetchQuery({
      queryKey: [key],
      queryFn: async () => {
        throw new NetworkError('Network request failed')
      },
    })
    .catch(() => undefined)
}

async function failedAction(client: QueryClient, label: string, onRun?: () => void) {
  const mutation = client.getMutationCache().build(client, {
    mutationFn: (async () => {
      onRun?.()
      throw new Error('nope')
    }) as never,
    meta: { label },
    retry: false,
  })
  await mutation.execute(undefined as never).catch(() => undefined)
}

afterEach(() => onlineManager.setOnline(true))

describe('StatusBanner', () => {
  it('says nothing while the polls are landing', async () => {
    const client = newClient()
    await landed(client)

    renderBanner(client)

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says how old the screen is once it has gone quiet, not before', async () => {
    jest.useFakeTimers()
    try {
      const client = newClient()
      const now = Date.now()
      await landed(client, 'inventory', now - STALE_AFTER_MS + 30_000)
      renderBanner(client)
      expect(screen.queryByRole('status')).not.toBeInTheDocument()

      const query = client.getQueryCache().find({ queryKey: ['inventory'] })!
      act(() => {
        query.setState({ ...query.state, dataUpdatedAt: now - STALE_AFTER_MS - 1000 })
      })

      expect(await screen.findByRole('status')).toHaveTextContent(/Last updated .* ago/)
    } finally {
      jest.useRealTimers()
    }
  })

  it('says the server is not answering, and still leaves the stock on screen', async () => {
    const client = newClient()
    await landed(client)
    renderBanner(client)

    await act(async () => {
      await failed(client, 'receipts')
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Not reaching the kitchen server/i)
    expect(alert).toHaveTextContent(/showing stock from/i)
  })

  it('offers to try again, and clears when the server answers', async () => {
    const client = newClient()
    let reachable = false
    renderBanner(client)
    await act(async () => {
      // The same query, failing while the server is down and landing once it is back
      await client
        .fetchQuery({
          queryKey: ['inventory'],
          queryFn: async () => {
            if (!reachable) throw new NetworkError('Network request failed')
            return 'ok'
          },
        })
        .catch(() => undefined)
    })
    await screen.findByRole('alert')

    reachable = true
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })

  it('keeps a failed action where it can be seen, and retries it', async () => {
    const client = newClient()
    let runs = 0
    renderBanner(client)

    await act(async () => {
      await failedAction(client, 'Consume', () => {
        runs += 1
      })
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Consume failed')
    fireEvent.click(screen.getByRole('button', { name: 'Retry Consume' }))
    await waitFor(() => expect(runs).toBe(2))
  })

  it('can be waved away when the cook has dealt with it', async () => {
    const client = newClient()
    renderBanner(client)
    await act(async () => {
      await failedAction(client, 'Consume')
    })
    await screen.findByRole('alert')

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Consume' }))

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })

  it('leads with what failed when the server is also unreachable', async () => {
    // Both are true at once when the API goes down mid-tap; the failed tap is the actionable one.
    const client = newClient()
    renderBanner(client)

    await act(async () => {
      await failed(client)
      await failedAction(client, 'Consume')
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Consume failed')
  })

  it('counts the rest when several things failed', async () => {
    const client = newClient()
    renderBanner(client)

    await act(async () => {
      for (const label of ['Consume', 'Save', 'Quick add', 'Clear']) {
        await failedAction(client, label)
      }
    })

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('and 1 more')
  })
})
