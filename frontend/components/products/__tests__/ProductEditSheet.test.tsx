/**
 * Correcting a product (H18).
 *
 * A product's shelf life, piece weight and unit are learned from the first receipt
 * that created it. Until this sheet there was no way to fix any of them, so a wrong
 * first guess was permanent: mince guessed at 5 days marks every future pack expired
 * on day six.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import ProductEditSheet from '../ProductEditSheet'
import type { Category } from '@/types/category'
import type { ProductMaster, ProductNames } from '@/types/product'

const CATEGORIES: Category[] = [
  {
    id: 'meat',
    display_name: 'Meat',
    icon: '🥩',
    default_shelf_life_days: 5,
    frozen_shelf_life_days: 180,
    sort_order: 1,
    default_storage: 'refrigerator',
    shelf_life_min_days: 1,
    shelf_life_max_days: 60,
  },
  {
    id: 'fish',
    display_name: 'Fish',
    icon: '🐟',
    default_shelf_life_days: 3,
    frozen_shelf_life_days: 120,
    sort_order: 2,
    default_storage: 'refrigerator',
    shelf_life_min_days: 1,
    shelf_life_max_days: 60,
  },
]

const NAMES: ProductNames = {
  names: [
    { id: 'n-own', name: 'ground beef', source: 'canonical', removable: false },
    { id: 'n-cook', name: 'jauheliha', source: 'cook', removable: true },
    { id: 'n-guess', name: 'minced pork', source: 'model', removable: true },
  ],
  printed: [
    {
      id: 'a-1',
      store_chain: 's-market',
      receipt_name: 'NAUDAN JAUHELIHA 400G',
      source: 'model',
      verified: false,
      occurrence_count: 2,
      last_seen: '2026-09-20T10:00:00Z',
    },
  ],
}

const EMOJI_REFERENCE = [
  { emoji: '🥩', name: 'cut of meat' },
  { emoji: '🥨', name: 'pretzel' },
  { emoji: '🧀', name: 'cheese wedge' },
]

// The sheet polls `GET /products/{id}` while its icon is pending (F4 review). Most tests
// never make it pending, so the poll's request goes unhandled (MSW logs it, harmlessly -
// `polled.data` just stays undefined and `liveProduct` falls through to `product`/
// `liveAnswer` as before); only the dedicated polling test below gives it a handler.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => {
  server.use(
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
    http.get(`${API_URL}/products/p-1/names`, () => HttpResponse.json(NAMES)),
    http.get(`${API_URL}/products/emoji/reference`, () =>
      HttpResponse.json(EMOJI_REFERENCE)
    )
  )
})
afterEach(() => {
  server.resetHandlers()
  jest.useRealTimers()
})
afterAll(() => server.close())

const PRODUCT: ProductMaster = {
  id: 'p-1',
  canonical_name: 'Ground beef',
  category: 'meat',
  storage_type: 'refrigerator',
  default_shelf_life_days: 5,
  opened_shelf_life_days: null,
  frozen_shelf_life_days: null,
  avg_piece_grams: null,
  pack_grams: null,
  shelf_life_source: 'category',
  unit_type: 'weight',
  default_unit: 'g',
  default_quantity: 400,
  min_stock_quantity: null,
  reorder_quantity: null,
  off_product_id: null,
  off_data: null,
  generation_enabled: true,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

function mockApi(response?: () => Response) {
  const patches: Record<string, unknown>[] = []
  server.use(
    http.patch(`${API_URL}/products/p-1`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>
      patches.push(body)
      return response?.() ?? HttpResponse.json({ ...PRODUCT, ...body })
    })
  )
  return patches
}

function renderSheet(product: ProductMaster = PRODUCT, onClose = jest.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const sheet = (current: ProductMaster) => (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ProductEditSheet product={current} onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  const { rerender } = render(sheet(product))
  // What a refetch, or another cook, does to an open sheet
  moved = (next: Partial<ProductMaster>) => rerender(sheet({ ...product, ...next }))
  return onClose
}

let moved: (next: Partial<ProductMaster>) => void

const save = () => screen.getByRole('button', { name: 'Save' })

describe('ProductEditSheet', () => {
  it('prefills from the product', () => {
    renderSheet()

    expect(screen.getByLabelText('Name')).toHaveValue('Ground beef')
    expect(screen.getByLabelText('Keeps for')).toHaveValue(5)
    expect(screen.getByLabelText('Once opened')).toHaveValue(null)
  })

  it('sends only what changed', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('Keeps for'), { target: { value: '3' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ default_shelf_life_days: 3 })
  })

  it('cannot be saved until something changes', () => {
    renderSheet()

    expect(save()).toBeDisabled()
  })

  it('clears a value the cook empties', async () => {
    const patches = mockApi()
    renderSheet({ ...PRODUCT, opened_shelf_life_days: 3 })

    fireEvent.change(screen.getByLabelText('Once opened'), { target: { value: '' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ opened_shelf_life_days: null })
  })

  it('refuses a shelf life that is not a positive number', () => {
    renderSheet()

    fireEvent.change(screen.getByLabelText('Keeps for'), { target: { value: '0' } })

    // Every expiry date comes from this field, so it may not be blank or zero.
    expect(save()).toBeDisabled()
  })

  it('sends the unit without a unit type', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.click(screen.getByRole('radio', { name: 'pcs' }))
    fireEvent.change(screen.getByLabelText('One piece'), { target: { value: '110' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    // unit_type is derived server-side from default_unit; sending it would fight that.
    expect(patches[0]).toEqual({ default_unit: 'pcs', avg_piece_grams: 110 })
    expect(patches[0]).not.toHaveProperty('unit_type')
  })

  it('remembers what one pack weighs', async () => {
    // Q8: the receipt prints `1 pcs` of mince and never says 400 g, so the cook says it
    // once here and every later receipt from any shop stores grams.
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('One pack'), { target: { value: '400' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ pack_grams: 400 })
  })

  it('clears a pack weight that was wrong', async () => {
    const patches = mockApi()
    renderSheet({ ...PRODUCT, pack_grams: 400 })

    expect(screen.getByLabelText('One pack')).toHaveValue(400)
    fireEvent.change(screen.getByLabelText('One pack'), { target: { value: '' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ pack_grams: null })
  })

  it('closes on success', async () => {
    mockApi()
    const onClose = renderSheet()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Minced beef' } })
    fireEvent.click(save())

    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('keeps the sheet open and shows the reason when the API refuses', async () => {
    mockApi(() =>
      HttpResponse.json({ detail: 'Record already exists.' }, { status: 409 })
    )
    const onClose = renderSheet()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Milk' } })
    fireEvent.click(save())

    expect(await screen.findByText('Record already exists.')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('while the product moves underneath the sheet (H25)', () => {
  it('follows the server for a field nobody has touched', () => {
    renderSheet()

    moved({ default_shelf_life_days: 9 })

    expect(screen.getByLabelText('Keeps for')).toHaveValue(9)
    expect(save()).toBeDisabled()
  })

  it('does not arm Save by itself', () => {
    renderSheet()

    moved({ canonical_name: 'Minced beef', default_shelf_life_days: 9 })

    expect(save()).toBeDisabled()
  })

  it('sends only the field the cook touched', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Minced beef' } })
    moved({ default_shelf_life_days: 9 })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ canonical_name: 'Minced beef' })
  })

  it('says so when a field the cook is editing moved as well', () => {
    renderSheet()

    fireEvent.change(screen.getByLabelText('Keeps for'), { target: { value: '3' } })
    moved({ default_shelf_life_days: 9 })

    expect(screen.getByRole('status')).toHaveTextContent(
      'Keeps for changed to 9 while this was open'
    )
  })
})

describe('category and frozen life (H52)', () => {
  it('moves the product to another category', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.click(await screen.findByRole('radio', { name: /Fish/ }))
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ category: 'fish' })
  })

  it('says a placeholder shelf life follows the category', async () => {
    renderSheet()

    expect(await screen.findByText(/follows the category/)).toBeInTheDocument()
  })

  it('does not say so once the cook has set the shelf life', async () => {
    renderSheet({ ...PRODUCT, shelf_life_source: 'cook' })

    await screen.findByRole('radio', { name: /Fish/ })
    expect(screen.queryByText(/follows the category/)).not.toBeInTheDocument()
  })

  it("shows the category's frozen life when the product has none", async () => {
    renderSheet()

    expect(await screen.findByPlaceholderText('180')).toBeInTheDocument()
    expect(screen.getByLabelText('Once frozen')).toHaveValue(null)
  })

  it('sets a frozen life of its own', async () => {
    const patches = mockApi()
    renderSheet()

    fireEvent.change(screen.getByLabelText('Once frozen'), { target: { value: '30' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ frozen_shelf_life_days: 30 })
  })

  it('clearing it hands the frozen life back to the category', async () => {
    const patches = mockApi()
    renderSheet({ ...PRODUCT, frozen_shelf_life_days: 30 })

    fireEvent.change(screen.getByLabelText('Once frozen'), { target: { value: '' } })
    fireEvent.click(save())

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0]).toEqual({ frozen_shelf_life_days: null })
  })

  it('says so when the category moved while the sheet was open', async () => {
    renderSheet()

    fireEvent.click(await screen.findByRole('radio', { name: /Fish/ }))
    moved({ category: 'dairy' })

    expect(screen.getByRole('status')).toHaveTextContent('Category changed')
  })
})

describe('matching names (H52)', () => {
  it('lists the names with whose word each is', async () => {
    renderSheet()

    const guess = await screen.findByText('minced pork')
    expect(guess.closest('li')).toHaveTextContent('auto')
    expect(screen.getByText('jauheliha').closest('li')).toHaveTextContent('yours')
    expect(screen.getByText('NAUDAN JAUHELIHA 400G').closest('li')).toHaveTextContent(
      's-market'
    )
  })

  it('offers no way to remove the product’s own name', async () => {
    renderSheet()

    await screen.findByText('ground beef')
    expect(
      screen.queryByRole('button', { name: 'Remove ground beef' })
    ).not.toBeInTheDocument()
  })

  it('removes a name on the second tap', async () => {
    const removed: string[] = []
    let names = NAMES
    server.use(
      http.get(`${API_URL}/products/p-1/names`, () => HttpResponse.json(names)),
      http.delete(`${API_URL}/products/p-1/names/:nameId`, ({ params }) => {
        removed.push(String(params.nameId))
        names = { ...names, names: names.names.filter((n) => n.id !== params.nameId) }
        return new HttpResponse(null, { status: 204 })
      })
    )
    renderSheet()

    const remove = await screen.findByRole('button', { name: 'Remove minced pork' })
    fireEvent.click(remove)
    expect(removed).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'Confirm remove minced pork' }))

    await waitFor(() => expect(removed).toEqual(['n-guess']))
    await waitFor(() => expect(screen.queryByText('minced pork')).not.toBeInTheDocument())
  })

  it('removes a printed name through its own route', async () => {
    const removed: string[] = []
    server.use(
      http.delete(`${API_URL}/products/p-1/aliases/:aliasId`, ({ params }) => {
        removed.push(String(params.aliasId))
        return new HttpResponse(null, { status: 204 })
      })
    )
    renderSheet()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Remove NAUDAN JAUHELIHA 400G' })
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Confirm remove NAUDAN JAUHELIHA 400G' })
    )

    await waitFor(() => expect(removed).toEqual(['a-1']))
  })
})

// Q18-G2: the product's own generated image, regenerated on request (with the cook's words,
// a new seed each time) or dropped for the category emoji. Loads only as an <img>.
describe('ProductEditSheet icon', () => {
  const GENERATED: ProductMaster = { ...PRODUCT, icon_status: 'ready', icon_version: 1790000000 }

  function iconSection() {
    return screen.getByRole('group', { name: 'Icon' })
  }

  it('shows the category emoji when there is no generated image', async () => {
    renderSheet()

    await waitFor(() => expect(iconSection()).toHaveTextContent('🥩'))
    expect(iconSection().querySelector('img')).toBeNull()
  })

  it('shows the generated image when there is one', () => {
    renderSheet(GENERATED)

    const img = iconSection().querySelector('img')
    expect(img?.getAttribute('src')).toMatch(/\/products\/p-1\/icon\.png\?v=1790000000$/)
    expect(img).toHaveAttribute('alt', '')
  })

  it('regenerates with the hint and says it is generating', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post(`${API_URL}/products/p-1/icon`, async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({ ...GENERATED, icon_status: 'pending' }, { status: 202 })
      })
    )
    renderSheet(GENERATED)

    fireEvent.change(screen.getByLabelText('Hint for the image'), {
      target: { value: 'dark loaf with seeds' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }))

    await waitFor(() => expect(bodies).toEqual([{ hint: 'dark loaf with seeds' }]))
    expect(
      await screen.findByText('Generating… this takes a few minutes')
    ).toBeInTheDocument()
  })

  it('says a pending render is on its way', () => {
    renderSheet({ ...PRODUCT, icon_status: 'pending' })

    expect(screen.getByText('Generating… this takes a few minutes')).toBeInTheDocument()
  })

  it('says when the last render failed', () => {
    renderSheet({ ...PRODUCT, icon_status: 'failed' })

    expect(iconSection()).toHaveTextContent(/could not generate/i)
  })

  it('drops the image for the category emoji', async () => {
    let deleted = false
    server.use(
      http.delete(`${API_URL}/products/p-1/icon`, () => {
        deleted = true
        return HttpResponse.json({ ...PRODUCT, icon_status: 'cleared', icon_version: null })
      })
    )
    renderSheet(GENERATED)

    fireEvent.click(screen.getByRole('button', { name: 'Use category emoji' }))

    await waitFor(() => expect(deleted).toBe(true))
    await waitFor(() => expect(iconSection().querySelector('img')).toBeNull())
    expect(iconSection()).toHaveTextContent('🥩')
  })

  it('offers no emoji button when the emoji is already what shows', () => {
    renderSheet({ ...PRODUCT, icon_status: 'cleared' })

    expect(screen.queryByRole('button', { name: 'Use category emoji' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Regenerate' })).toBeEnabled()
  })

  it('does not count the hint as an unsaved product change', () => {
    renderSheet()

    fireEvent.change(screen.getByLabelText('Hint for the image'), {
      target: { value: 'round' },
    })

    expect(save()).toBeDisabled()
  })

  it(
    'clears "Generating..." on its own once a poll finds the icon ready (F4)',
    async () => {
      let polls = 0
      server.use(
        http.get(`${API_URL}/products/p-1`, () => {
          polls += 1
          return HttpResponse.json(
            polls === 1
              ? { ...PRODUCT, icon_status: 'pending' }
              : {
                  ...PRODUCT,
                  icon_status: 'ready',
                  icon_version: 1790000001,
                  updated_at: '2026-09-01T00:00:10Z',
                }
          )
        })
      )
      renderSheet({ ...PRODUCT, icon_status: 'pending' })

      expect(
        screen.getByText('Generating… this takes a few minutes')
      ).toBeInTheDocument()

      await waitFor(
        () =>
          expect(
            screen.queryByText('Generating… this takes a few minutes')
          ).toBeNull(),
        { timeout: 8000, interval: 250 }
      )
      expect(polls).toBeGreaterThan(1)
    },
    10_000
  )

  it('shows a plain note instead of Regenerate when generation is not configured', () => {
    renderSheet({ ...PRODUCT, generation_enabled: false })

    expect(
      screen.getByText('Icon generation is not configured on this server')
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Regenerate' })).toBeNull()
    expect(screen.queryByLabelText('Hint for the image')).toBeNull()
  })

  it('still offers Use category emoji when generation is not configured', () => {
    renderSheet({ ...GENERATED, generation_enabled: false })

    expect(screen.getByRole('button', { name: 'Use category emoji' })).toBeInTheDocument()
  })
})

// Q18 build: the exact emoji, ahead of the generated image in the same preview. A proposal shows
// Confirm/Reject; otherwise a picker limited to the reference list, plus "No emoji".
describe('ProductEditSheet emoji', () => {
  function emojiSection() {
    return screen.getByRole('group', { name: 'Emoji' })
  }

  it('shows the emoji ahead of the generated image', async () => {
    renderSheet({
      ...PRODUCT,
      icon_status: 'ready',
      icon_version: 1790000000,
      emoji: '🧀',
      emoji_match: 'exact',
    })

    await waitFor(() => expect(screen.getByRole('group', { name: 'Icon' })).toHaveTextContent('🧀'))
    expect(screen.getByRole('group', { name: 'Icon' }).querySelector('img')).toBeNull()
  })

  it('offers the reference list, plus No emoji', async () => {
    renderSheet()

    await screen.findByRole('button', { name: 'cut of meat' })
    expect(screen.getByRole('button', { name: 'pretzel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'cheese wedge' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'No emoji' })).toBeInTheDocument()
  })

  it('marks a table-set exact emoji as the picker selection, not just a cook pick', async () => {
    renderSheet({ ...PRODUCT, emoji: '🧀', emoji_match: 'exact' })

    const selected = await screen.findByRole('button', { name: 'cheese wedge' })

    expect(selected).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'pretzel' })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
  })

  it('picking one puts it to the cook, at once, without Save', async () => {
    let body: unknown
    server.use(
      http.put(`${API_URL}/products/p-1/emoji`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...PRODUCT, emoji: '🥨', emoji_match: 'cook' })
      })
    )
    renderSheet()

    fireEvent.click(await screen.findByRole('button', { name: 'pretzel' }))

    await waitFor(() => expect(body).toEqual({ emoji: '🥨' }))
    expect(await screen.findByText('Your own choice')).toBeInTheDocument()
    expect(save()).toBeDisabled()
  })

  it('No emoji clears it', async () => {
    let body: unknown
    server.use(
      http.put(`${API_URL}/products/p-1/emoji`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...PRODUCT, emoji: null, emoji_match: 'cleared' })
      })
    )
    renderSheet({ ...PRODUCT, emoji: '🧀', emoji_match: 'exact' })

    fireEvent.click(await screen.findByRole('button', { name: 'No emoji' }))

    await waitFor(() => expect(body).toEqual({ emoji: null }))
  })

  it('a proposal shows Confirm and Reject, and no other emoji is shown yet', async () => {
    renderSheet({ ...PRODUCT, emoji: '🥨', emoji_match: 'proposed' })

    await waitFor(() => expect(emojiSection()).toHaveTextContent('🥨'))
    expect(emojiSection()).toHaveTextContent('waiting to be confirmed')
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    // A proposal is never shown as the icon until it is confirmed.
    expect(screen.getByRole('group', { name: 'Icon' })).not.toHaveTextContent('🥨')
  })

  it('confirming makes it exact', async () => {
    server.use(
      http.post(`${API_URL}/products/p-1/emoji/confirm`, () =>
        HttpResponse.json({ ...PRODUCT, emoji: '🥨', emoji_match: 'exact' })
      )
    )
    renderSheet({ ...PRODUCT, emoji: '🥨', emoji_match: 'proposed' })

    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }))

    expect(await screen.findByText('Exact match')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('group', { name: 'Icon' })).toHaveTextContent('🥨')
    )
  })

  it('rejecting drops it to the gap list', async () => {
    server.use(
      http.post(`${API_URL}/products/p-1/emoji/reject`, () =>
        HttpResponse.json({ ...PRODUCT, emoji: null, emoji_match: 'none' })
      )
    )
    renderSheet({ ...PRODUCT, emoji: '🥨', emoji_match: 'proposed' })

    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull())
  })
})
