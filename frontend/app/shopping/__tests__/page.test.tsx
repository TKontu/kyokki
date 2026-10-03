/**
 * The Shopping screen: open items grouped Urgent / Normal / Low, bought items collapsed below,
 * quick-add, tick with undo, remove, clear bought and generate - all against msw mocks shaped
 * exactly like the backend schemas (backend/app/schemas/shopping_list_item.py).
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import Shopping from '../page'
import type { ShoppingListItem } from '@/types/shopping'

const BANANAS: ShoppingListItem = {
  id: 'i-bananas',
  product_master_id: null,
  name: 'Bananas',
  quantity: 6,
  unit: 'pcs',
  priority: 'urgent',
  source: 'manual',
  is_purchased: false,
  added_at: '2026-10-01T08:00:00Z',
  purchased_at: null,
}

const MILK: ShoppingListItem = {
  ...BANANAS,
  id: 'i-milk',
  name: 'Oat Milk',
  priority: 'normal',
  unit: 'dl',
  quantity: 10,
}

const FLOUR: ShoppingListItem = {
  ...BANANAS,
  id: 'i-flour',
  name: 'Flour',
  priority: 'low',
  unit: 'g',
  quantity: 500,
}

const EGGS: ShoppingListItem = {
  ...BANANAS,
  id: 'i-eggs',
  name: 'Eggs',
  is_purchased: true,
  purchased_at: '2026-10-01T09:00:00Z',
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

/** The requests the screen can make; each test registers the rows it needs. */
function api(rows: ShoppingListItem[]) {
  let list = [...rows]
  const asked = {
    created: [] as unknown[],
    purchased: [] as Record<string, unknown>[],
    purchaseKeys: [] as Array<string | null>,
    removed: [] as string[],
    removeKeys: [] as Array<string | null>,
    cleared: 0,
    listCalls: 0,
  }
  server.use(
    http.get(`${API_URL}/shopping/`, () => {
      asked.listCalls += 1
      return HttpResponse.json(list)
    }),
    http.post(`${API_URL}/shopping/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      asked.created.push(body)
      const created: ShoppingListItem = {
        id: 'i-new',
        product_master_id: null,
        name: String(body.name),
        quantity: Number(body.quantity),
        unit: String(body.unit),
        priority: 'normal',
        source: 'manual',
        is_purchased: false,
        added_at: '2026-10-01T10:00:00Z',
        purchased_at: null,
      }
      list = [...list, created]
      return HttpResponse.json(created, { status: 201 })
    }),
    http.post(`${API_URL}/shopping/:id/purchase`, ({ request, params }) => {
      const purchased = new URL(request.url).searchParams.get('purchased') === 'true'
      asked.purchased.push({ id: params.id, purchased })
      asked.purchaseKeys.push(request.headers.get('Idempotency-Key'))
      list = list.map((item) =>
        item.id === params.id
          ? { ...item, is_purchased: purchased, purchased_at: purchased ? '2026-10-01T11:00:00Z' : null }
          : item
      )
      return HttpResponse.json(list.find((item) => item.id === params.id))
    }),
    http.delete(`${API_URL}/shopping/purchased/all`, () => {
      const before = list.length
      list = list.filter((item) => !item.is_purchased)
      asked.cleared = before - list.length
      return HttpResponse.json({ deleted_count: asked.cleared })
    }),
    http.delete(`${API_URL}/shopping/:id`, ({ request, params }) => {
      asked.removed.push(String(params.id))
      asked.removeKeys.push(request.headers.get('Idempotency-Key'))
      list = list.filter((item) => item.id !== params.id)
      return new HttpResponse(null, { status: 204 })
    }),
    http.post(`${API_URL}/shopping/generate`, () =>
      HttpResponse.json({ added: [], updated: [], unchanged: [], skipped: [], dry_run: true })
    )
  )
  return asked
}

function renderShopping() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <Shopping />
      </ToastProvider>
    </QueryClientProvider>
  )
}

describe('The Shopping screen', () => {
  it('groups open items Urgent, Normal, Low, urgent first', async () => {
    api([FLOUR, MILK, BANANAS])

    renderShopping()

    const urgent = (await screen.findByRole('heading', { name: 'Urgent' })).closest(
      'section'
    ) as HTMLElement
    expect(within(urgent).getByText('Bananas')).toBeInTheDocument()
    const headings = (await screen.findAllByRole('heading', { level: 2 })).map((h) => h.textContent)
    expect(headings).toEqual(['Urgent', 'Normal', 'Low'])
  })

  it('shows bought items collapsed, with a count and Clear bought', async () => {
    api([BANANAS, EGGS])

    renderShopping()

    expect(await screen.findByText(/Bought \(1\)/)).toBeInTheDocument()
    expect(screen.queryByText('Eggs')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear bought' })).toBeInTheDocument()
  })

  it('expands the bought section on tap', async () => {
    api([EGGS])
    renderShopping()

    fireEvent.click(await screen.findByText(/Bought \(1\)/))

    expect(await screen.findByText('Eggs')).toBeInTheDocument()
  })

  it('adds an item by name', async () => {
    const asked = api([])

    renderShopping()
    await screen.findByText('Nothing on the list.')

    fireEvent.change(screen.getByLabelText('Item name'), { target: { value: 'Bananas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(asked.created).toEqual([{ name: 'Bananas', quantity: 1, unit: 'pcs' }]))
    expect(await screen.findByText('Bananas')).toBeInTheDocument()
  })

  it('ticks an item bought, with an undo toast', async () => {
    const asked = api([BANANAS])

    renderShopping()
    await screen.findByText('Bananas')

    fireEvent.click(screen.getByRole('button', { name: 'Mark Bananas bought' }))

    await waitFor(() => expect(asked.purchased).toEqual([{ id: 'i-bananas', purchased: true }]))
    expect(await screen.findByText('Bought · Bananas')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))

    await waitFor(() =>
      expect(asked.purchased).toEqual([
        { id: 'i-bananas', purchased: true },
        { id: 'i-bananas', purchased: false },
      ])
    )
    // F1: the tick and the undo are two different user actions, so each mints its own key.
    expect(asked.purchaseKeys[0]).toBeTruthy()
    expect(asked.purchaseKeys[1]).toBeTruthy()
    expect(asked.purchaseKeys[0]).not.toBe(asked.purchaseKeys[1])
  })

  it('retries a failed tick with the same Idempotency-Key (F1)', async () => {
    let attempts = 0
    const headers: Array<string | null> = []
    server.use(
      http.get(`${API_URL}/shopping/`, () => HttpResponse.json([BANANAS])),
      http.post(`${API_URL}/shopping/:id/purchase`, ({ request }) => {
        attempts += 1
        headers.push(request.headers.get('Idempotency-Key'))
        if (attempts === 1) {
          return HttpResponse.json({ detail: 'boom' }, { status: 500 })
        }
        return HttpResponse.json({ ...BANANAS, is_purchased: true })
      })
    )

    renderShopping()
    await screen.findByText('Bananas')

    fireEvent.click(screen.getByRole('button', { name: 'Mark Bananas bought' }))
    expect(await screen.findByText('Could not update Bananas')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(attempts).toBe(2))

    expect(headers[0]).toBeTruthy()
    expect(headers[0]).toBe(headers[1])
  })

  it("tells the cook when undo fails, and refetches the list (F2)", async () => {
    let listCalls = 0
    server.use(
      http.get(`${API_URL}/shopping/`, () => {
        listCalls += 1
        return HttpResponse.json([BANANAS])
      }),
      http.post(`${API_URL}/shopping/:id/purchase`, ({ request }) => {
        const purchased = new URL(request.url).searchParams.get('purchased') === 'true'
        if (!purchased) {
          return HttpResponse.json({ detail: 'boom' }, { status: 500 })
        }
        return HttpResponse.json({ ...BANANAS, is_purchased: true })
      })
    )

    renderShopping()
    await screen.findByText('Bananas')

    fireEvent.click(screen.getByRole('button', { name: 'Mark Bananas bought' }))
    await screen.findByText('Bought · Bananas')
    const callsBeforeUndo = listCalls

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))

    expect(await screen.findByText("Couldn't undo; it's still ticked")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    // F2: a failed undo refetches the list, rather than leaving a possibly stale cache.
    await waitFor(() => expect(listCalls).toBeGreaterThan(callsBeforeUndo))
  })

  it('removes an item', async () => {
    const asked = api([BANANAS])

    renderShopping()
    await screen.findByText('Bananas')

    fireEvent.click(screen.getByRole('button', { name: 'Remove Bananas' }))

    await waitFor(() => expect(asked.removed).toEqual(['i-bananas']))
    await waitFor(() => expect(screen.queryByText('Bananas')).not.toBeInTheDocument())
  })

  it('removes an item with its own Idempotency-Key, minted once per action (#159 folded fix)', async () => {
    const asked = api([BANANAS])

    renderShopping()
    await screen.findByText('Bananas')

    fireEvent.click(screen.getByRole('button', { name: 'Remove Bananas' }))

    await waitFor(() => expect(asked.removeKeys).toHaveLength(1))
    expect(asked.removeKeys[0]).toBeTruthy()
    expect(asked.removeKeys[0]).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    )
  })

  it('clears bought items', async () => {
    const asked = api([BANANAS, EGGS])

    renderShopping()
    await screen.findByText(/Bought \(1\)/)

    fireEvent.click(screen.getByRole('button', { name: 'Clear bought' }))

    await waitFor(() => expect(asked.cleared).toBe(1))
    await waitFor(() => expect(screen.queryByText(/Bought \(/)).not.toBeInTheDocument())
  })

  it('opens the generate sheet', async () => {
    api([])
    renderShopping()
    await screen.findByText('Nothing on the list.')

    fireEvent.click(screen.getByRole('button', { name: 'Generate from low stock' }))

    expect(await screen.findByRole('dialog', { name: 'Generate from low stock' })).toBeInTheDocument()
  })

  it('has nothing to show when the list is empty', async () => {
    api([])
    renderShopping()

    expect(await screen.findByText('Nothing on the list.')).toBeInTheDocument()
  })

  describe('display language (Post-MVP frontier item 13, phase 2)', () => {
    afterEach(() => window.localStorage.clear())

    it('reads the header, groups and empty state in Finnish', async () => {
      window.localStorage.setItem('kyokki.language', 'fi')
      api([BANANAS])
      renderShopping()

      expect(await screen.findByRole('heading', { name: 'Ostoslista' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Luo vähissä olevista' })).toBeInTheDocument()
      expect(await screen.findByRole('heading', { name: 'Kiireelliset' })).toBeInTheDocument()
    })

    it('reads "Nothing on the list" in Finnish', async () => {
      window.localStorage.setItem('kyokki.language', 'fi')
      api([])
      renderShopping()

      expect(await screen.findByText('Listalla ei ole mitään.')).toBeInTheDocument()
    })
  })
})
