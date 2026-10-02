/**
 * The product icon calls (Q18): the image URL, Redraw and Use category emoji. Also the
 * exact emoji calls (Q18 build): the reference list, the cook's own choice, and confirm/reject.
 */

import productsAPI, {
  clearIcon,
  confirmEmoji,
  emojiReference,
  iconUrl,
  redrawIcon,
  rejectEmoji,
  setEmoji,
} from '../products'
import { server, API_URL } from '@/test/msw/server'
import { http, HttpResponse } from 'msw'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('iconUrl', () => {
  it('points at the served SVG with the version, so a redraw is a new URL', () => {
    expect(iconUrl('p-1', 1790000000)).toBe(`${API_URL}/products/p-1/icon.png?v=1790000000`)
  })

  it('escapes the id', () => {
    expect(iconUrl('a/b', 1)).toBe(`${API_URL}/products/a%2Fb/icon.png?v=1`)
  })

  it('is on the default export too', () => {
    expect(productsAPI.iconUrl).toBe(iconUrl)
  })

  it('uses the client base URL, so the two cannot drift', () => {
    const { API_BASE_URL } = jest.requireActual('../client')
    expect(iconUrl('p-1', 1).startsWith(`${API_BASE_URL}/products/`)).toBe(true)
  })

  it('falls back to the same-origin /api path the middleware authenticates', () => {
    const saved = process.env.NEXT_PUBLIC_API_URL
    delete process.env.NEXT_PUBLIC_API_URL
    try {
      jest.isolateModules(() => {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const fresh = require('../products') as typeof import('../products')
        expect(fresh.iconUrl('p-1', 7)).toBe('/api/products/p-1/icon.png?v=7')
      })
    } finally {
      process.env.NEXT_PUBLIC_API_URL = saved
    }
  })
})

describe('redrawIcon', () => {
  it('posts the hint and returns the product', async () => {
    let body: unknown
    server.use(
      http.post(`${API_URL}/products/p-1/icon`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'p-1', icon_status: 'pending' }, { status: 202 })
      })
    )

    const product = await redrawIcon('p-1', 'oval rye pastry')

    expect(body).toEqual({ hint: 'oval rye pastry' })
    expect(product.icon_status).toBe('pending')
  })

  it('sends a null hint when there is none', async () => {
    let body: unknown
    server.use(
      http.post(`${API_URL}/products/p-1/icon`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'p-1', icon_status: 'pending' }, { status: 202 })
      })
    )

    await redrawIcon('p-1')

    expect(body).toEqual({ hint: null })
  })
})

describe('clearIcon', () => {
  it('deletes the icon and returns the product', async () => {
    server.use(
      http.delete(`${API_URL}/products/p-1/icon`, () =>
        HttpResponse.json({ id: 'p-1', icon_status: 'cleared', icon_version: null })
      )
    )

    const product = await clearIcon('p-1')

    expect(product.icon_status).toBe('cleared')
  })
})

describe('emojiReference', () => {
  it('lists the pickable emoji', async () => {
    server.use(
      http.get(`${API_URL}/products/emoji/reference`, () =>
        HttpResponse.json([{ emoji: '🥦', name: 'broccoli' }])
      )
    )

    const entries = await emojiReference()

    expect(entries).toEqual([{ emoji: '🥦', name: 'broccoli' }])
  })
})

describe('setEmoji', () => {
  it('puts the chosen emoji', async () => {
    let body: unknown
    server.use(
      http.put(`${API_URL}/products/p-1/emoji`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'p-1', emoji: '🥨', emoji_match: 'cook' })
      })
    )

    const product = await setEmoji('p-1', '🥨')

    expect(body).toEqual({ emoji: '🥨' })
    expect(product.emoji_match).toBe('cook')
  })

  it('puts null to clear it', async () => {
    let body: unknown
    server.use(
      http.put(`${API_URL}/products/p-1/emoji`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ id: 'p-1', emoji: null, emoji_match: 'cleared' })
      })
    )

    await setEmoji('p-1', null)

    expect(body).toEqual({ emoji: null })
  })
})

describe('confirmEmoji', () => {
  it('posts to confirm and returns the product', async () => {
    server.use(
      http.post(`${API_URL}/products/p-1/emoji/confirm`, () =>
        HttpResponse.json({ id: 'p-1', emoji: '🥨', emoji_match: 'exact' })
      )
    )

    const product = await confirmEmoji('p-1')

    expect(product.emoji_match).toBe('exact')
  })
})

describe('rejectEmoji', () => {
  it('posts to reject and returns the product', async () => {
    server.use(
      http.post(`${API_URL}/products/p-1/emoji/reject`, () =>
        HttpResponse.json({ id: 'p-1', emoji: null, emoji_match: 'none' })
      )
    )

    const product = await rejectEmoji('p-1')

    expect(product.emoji_match).toBe('none')
  })
})
