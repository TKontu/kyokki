/**
 * The shopping list API module: every call against backend/app/api/endpoints/shopping.py,
 * and the Idempotency-Key the API honours on create, purchase and an applied generate.
 */

import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import shoppingAPI, { newIdempotencyKey } from '../shopping'
import type { ShoppingGenerateResponse, ShoppingListItem } from '@/types/shopping'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

const ITEM: ShoppingListItem = {
  id: 'i-1',
  product_master_id: null,
  name: 'Bananas',
  quantity: 6,
  unit: 'pcs',
  priority: 'normal',
  source: 'manual',
  is_purchased: false,
  added_at: '2026-10-01T10:00:00Z',
  purchased_at: null,
}

describe('newIdempotencyKey', () => {
  it('returns a v4-shaped UUID', () => {
    const key = newIdempotencyKey()
    expect(key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    )
  })

  it('is different on every call', () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey())
  })
})

describe('list', () => {
  it('asks for the open list by default, and forwards include_purchased', async () => {
    let seen: URLSearchParams | undefined
    server.use(
      http.get(`${API_URL}/shopping/`, ({ request }) => {
        seen = new URL(request.url).searchParams
        return HttpResponse.json([ITEM])
      })
    )

    const items = await shoppingAPI.list({ include_purchased: true })

    expect(items).toEqual([ITEM])
    expect(seen?.get('include_purchased')).toBe('true')
  })
})

describe('create', () => {
  it('posts the item and sends the Idempotency-Key header', async () => {
    let body: unknown
    let header: string | null = null
    server.use(
      http.post(`${API_URL}/shopping/`, async ({ request }) => {
        body = await request.json()
        header = request.headers.get('Idempotency-Key')
        return HttpResponse.json(ITEM, { status: 201 })
      })
    )

    const item = await shoppingAPI.create(
      { name: 'Bananas', quantity: 6, unit: 'pcs' },
      'key-1'
    )

    expect(body).toEqual({ name: 'Bananas', quantity: 6, unit: 'pcs' })
    expect(header).toBe('key-1')
    expect(item).toEqual(ITEM)
  })
})

describe('purchase', () => {
  it('sends the purchased flag as a query param, with the Idempotency-Key header', async () => {
    let seen: URLSearchParams | undefined
    let header: string | null = null
    server.use(
      http.post(`${API_URL}/shopping/i-1/purchase`, ({ request }) => {
        seen = new URL(request.url).searchParams
        header = request.headers.get('Idempotency-Key')
        return HttpResponse.json({ ...ITEM, is_purchased: true })
      })
    )

    const item = await shoppingAPI.purchase('i-1', true, 'key-2')

    expect(seen?.get('purchased')).toBe('true')
    expect(header).toBe('key-2')
    expect(item.is_purchased).toBe(true)
  })

  it('can also unmark an item bought', async () => {
    let seen: URLSearchParams | undefined
    server.use(
      http.post(`${API_URL}/shopping/i-1/purchase`, ({ request }) => {
        seen = new URL(request.url).searchParams
        return HttpResponse.json({ ...ITEM, is_purchased: false })
      })
    )

    await shoppingAPI.purchase('i-1', false, 'key-3')

    expect(seen?.get('purchased')).toBe('false')
  })
})

describe('update', () => {
  it('patches the item', async () => {
    let body: unknown
    server.use(
      http.patch(`${API_URL}/shopping/i-1`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...ITEM, quantity: 3 })
      })
    )

    const item = await shoppingAPI.update('i-1', { quantity: 3 })

    expect(body).toEqual({ quantity: 3 })
    expect(item.quantity).toBe(3)
  })
})

describe('remove', () => {
  it('deletes the item', async () => {
    server.use(
      http.delete(`${API_URL}/shopping/i-1`, () => new HttpResponse(null, { status: 204 }))
    )

    await expect(shoppingAPI.remove('i-1')).resolves.toBeUndefined()
  })
})

describe('clearPurchased', () => {
  it('deletes every bought item', async () => {
    server.use(
      http.delete(`${API_URL}/shopping/purchased/all`, () =>
        HttpResponse.json({ deleted_count: 3 })
      )
    )

    await expect(shoppingAPI.clearPurchased()).resolves.toEqual({ deleted_count: 3 })
  })
})

describe('generate', () => {
  const RESPONSE: ShoppingGenerateResponse = {
    added: [],
    updated: [],
    unchanged: [],
    skipped: [],
    dry_run: true,
  }

  it('sends dry_run and the sources, without an Idempotency-Key on a dry run', async () => {
    let body: unknown
    let header: string | null = 'not-checked'
    server.use(
      http.post(`${API_URL}/shopping/generate`, async ({ request }) => {
        body = await request.json()
        header = request.headers.get('Idempotency-Key')
        return HttpResponse.json(RESPONSE)
      })
    )

    const result = await shoppingAPI.generate(
      { sources: ['low_stock'], dry_run: true },
      'ignored-on-a-dry-run'
    )

    expect(body).toEqual({ sources: ['low_stock'], dry_run: true })
    expect(header).toBeNull()
    expect(result.dry_run).toBe(true)
  })

  it('sends the Idempotency-Key header on an applied run', async () => {
    let header: string | null = null
    server.use(
      http.post(`${API_URL}/shopping/generate`, async ({ request }) => {
        header = request.headers.get('Idempotency-Key')
        return HttpResponse.json({ ...RESPONSE, dry_run: false })
      })
    )

    await shoppingAPI.generate({ sources: ['low_stock'], dry_run: false }, 'key-4')

    expect(header).toBe('key-4')
  })
})
