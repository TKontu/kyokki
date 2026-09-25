/**
 * The Gone screen (operator, 2026-09-22): what was thrown away or finished, newest first,
 * with a way back for anything still in the bin. Waste was recorded from MVP-S1 and invisible
 * until now.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import Gone from '../page'
import type { ConsumptionLogEntry, ConsumptionSummary } from '@/types/consumption'

const NOW = new Date('2026-09-22T12:00:00Z')

const MEAT: ConsumptionLogEntry = {
  id: 'l1',
  inventory_item_id: 'item-meat',
  item_status: 'discarded',
  product_master_id: 'p1',
  product_name: 'Minced Meat',
  unit: 'g',
  action: 'discard',
  quantity_consumed: 250,
  quantity_after: 0,
  logged_at: '2026-09-22T08:00:00Z',
}

const MILK: ConsumptionLogEntry = {
  ...MEAT,
  id: 'l2',
  inventory_item_id: 'item-milk',
  item_status: 'empty',
  product_name: 'Oat Milk',
  unit: 'dl',
  action: 'use_full',
  quantity_consumed: 10,
  logged_at: '2026-09-21T18:00:00Z',
}

const SUMMARY = {
  discard: { events: 8, totals: { g: 1400, pcs: 6 } },
  use_full: { events: 34, totals: { dl: 120 } },
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  jest.useFakeTimers({ doNotFake: ['setTimeout', 'clearTimeout', 'queueMicrotask'] })
  jest.setSystemTime(NOW)
})
afterEach(() => {
  jest.useRealTimers()
  server.resetHandlers()
})
afterAll(() => server.close())

/** The two requests the screen makes; `asked` records what it asked for. */
function api(rows: ConsumptionLogEntry[], summary: ConsumptionSummary = SUMMARY) {
  const asked: { list: URLSearchParams[]; patched: string[] } = { list: [], patched: [] }
  server.use(
    http.get(`${API_URL}/consumption-log/summary`, () => HttpResponse.json(summary)),
    http.get(`${API_URL}/consumption-log`, ({ request }) => {
      asked.list.push(new URL(request.url).searchParams)
      return HttpResponse.json(rows)
    }),
    http.patch(`${API_URL}/inventory/:id`, ({ params }) => {
      asked.patched.push(String(params.id))
      return HttpResponse.json({ id: params.id, status: 'opened' })
    })
  )
  return asked
}

function renderGone() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <Gone />
      </ToastProvider>
    </QueryClientProvider>
  )
}

describe('The Gone screen', () => {
  it('lists what left the kitchen, grouped by day, with no amounts', async () => {
    api([MEAT, MILK])

    renderGone()

    const today = (await screen.findByRole('heading', { name: 'Today' })).closest(
      'section'
    ) as HTMLElement
    expect(within(today).getByText('Minced Meat')).toBeInTheDocument()
    expect(within(today).queryByText(/250 g/)).not.toBeInTheDocument()
    const yesterday = screen.getByRole('heading', { name: 'Yesterday' }).closest(
      'section'
    ) as HTMLElement
    expect(within(yesterday).getByText('Oat Milk')).toBeInTheDocument()
  })

  it('says what the window cost, thrown away against eaten', async () => {
    api([MEAT, MILK])

    renderGone()

    expect(await screen.findByText('8 items')).toBeInTheDocument()
    expect(screen.getByText('34 items')).toBeInTheDocument()
  })

  it('asks for the last 30 days of what is gone', async () => {
    const asked = api([MEAT])

    renderGone()

    await waitFor(() => expect(asked.list).toHaveLength(1))
    const [params] = asked.list
    expect(params.getAll('action')).toEqual(['discard', 'use_full'])
    expect(params.get('since')).toBe('2026-08-23T12:00:00.000Z')
  })

  it('looks further back when asked, and all the way', async () => {
    const asked = api([MEAT])
    renderGone()
    await waitFor(() => expect(asked.list).toHaveLength(1))

    fireEvent.click(screen.getByRole('button', { name: '7 days' }))
    await waitFor(() => expect(asked.list).toHaveLength(2))
    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    await waitFor(() => expect(asked.list).toHaveLength(3))

    expect(asked.list[1].get('since')).toBe('2026-09-15T12:00:00.000Z')
    expect(asked.list[2].get('since')).toBeNull()
  })

  it('offers a way back for what is still in the bin, and nothing for what was eaten', async () => {
    const asked = api([MEAT, MILK])

    renderGone()

    expect(await screen.findByRole('button', { name: 'Put Minced Meat back' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Put Oat Milk back' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Put Minced Meat back' }))

    await waitFor(() => expect(asked.patched).toEqual(['item-meat']))
    expect(await screen.findByRole('status')).toHaveTextContent('Back in the kitchen · Minced Meat')
  })

  it('has nothing to show when nothing has gone', async () => {
    api([], {})

    renderGone()

    expect(await screen.findByText(/Nothing has been thrown away or finished/i)).toBeInTheDocument()
  })
})
