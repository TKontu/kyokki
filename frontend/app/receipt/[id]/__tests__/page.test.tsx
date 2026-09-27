/**
 * Receipt review page (MVP-R7): edit the read lines, skip what you do not want, confirm.
 */

import React from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import ReceiptReviewPage from '../page'
import { SEARCH_DEBOUNCE_MS } from '@/hooks/useProducts'
import type { ExtractedItem, Receipt, ReceiptStatus } from '@/types/receipt'

const push = jest.fn()
jest.mock('next/navigation', () => ({ useRouter: () => ({ push, back: jest.fn() }) }))

const CATEGORIES = [
  { id: 'dairy', display_name: 'Dairy & Eggs', icon: '🥛', default_shelf_life_days: 7, sort_order: 20, default_storage: 'refrigerator' },
  { id: 'meat', display_name: 'Meat & Poultry', icon: '🥩', default_shelf_life_days: 5, sort_order: 10, default_storage: 'refrigerator' },
]

function item(index: number, overrides: Partial<ExtractedItem> = {}): ExtractedItem {
  return {
    index,
    line_id: `line-${index}`,
    name: `PRINTED ${index}`,
    generic_name: `Generic ${index}`,
    quantity: 1,
    unit: 'pcs',
    product_id: null,
    product_name: null,
    match_score: null,
    match_confidence: null,
    match_source: null,
    verified: false,
    suggested_category: 'dairy',
    piece_grams: null,
    pack_grams: null,
    shelf_life_days: null,
    opened_shelf_life_days: null,
    non_food: false,
    printed_quantity: null,
    printed_unit: null,
    storage_type: 'refrigerator',
    location: 'main_fridge',
    ...overrides,
  }
}

/** A date N days before today, so an age-based test does not rot as the year moves on. */
function daysAgo(days: number): Date {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date
}

function isoDaysAgo(days: number): string {
  const date = daysAgo(days)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${String(date.getDate()).padStart(2, '0')}`
}

function finnishDaysAgo(days: number): string {
  const date = daysAgo(days)
  return `${date.getDate()}.${date.getMonth() + 1}.${date.getFullYear()}`
}

function receipt(overrides: Partial<Receipt> = {}, items: ExtractedItem[] = [item(0)]): Receipt {
  return {
    id: 'r1',
    store_chain: 's-group',
    // From this week, so the Q10 stale-receipt warning is opted into, not incidental.
    purchase_date: isoDaysAgo(3),
    image_path: 'data/receipts/r1.pdf',
    batch_id: null,
    ocr_raw_text: null,
    ocr_structured: null,
    processing_status: 'completed' as ReceiptStatus,
    error: null,
    queued_at: '2026-09-16T10:00:00Z',
    processing_started_at: '2026-09-16T10:00:03Z',
    items_extracted: items.length,
    items_matched: items.filter((i) => i.product_id).length,
    extraction_method: 'text',
    fallback_reason: null,
    items,
    created_at: '2026-09-16T10:00:00Z',
    ...overrides,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  push.mockReset()
})
afterAll(() => server.close())

const PRODUCTS = [
  {
    id: 'p-milk',
    canonical_name: 'Milk',
    category: 'dairy',
    storage_type: 'refrigerator',
    default_shelf_life_days: 7,
    opened_shelf_life_days: null,
    unit_type: 'volume',
    default_unit: 'dl',
    default_quantity: 10,
    min_stock_quantity: null,
    reorder_quantity: null,
    off_product_id: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  },
]

/** Step over the search debounce rather than waiting it out (H06). */
function search(term: string, inputId: string) {
  jest.useFakeTimers()
  fireEvent.change(document.getElementById(inputId) as HTMLInputElement, {
    target: { value: term },
  })
  act(() => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
  })
  jest.useRealTimers()
}

function mockApi(body: Receipt, confirmResponse?: () => Response) {
  const confirms: Record<string, unknown>[] = []
  // The fake keeps state like the API does: re-queueing changes what a refetch returns
  let current = body
  server.use(
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
    http.get(`${API_URL}/products`, ({ request }) => {
      const term = (new URL(request.url).searchParams.get('search') ?? '').toLowerCase()
      return HttpResponse.json(
        PRODUCTS.filter((p) => p.canonical_name.toLowerCase().includes(term))
      )
    }),
    http.get(`${API_URL}/receipts/r1`, () => HttpResponse.json(current)),
    http.post(`${API_URL}/receipts/r1/confirm`, async ({ request }) => {
      confirms.push((await request.json()) as Record<string, unknown>)
      return (
        confirmResponse?.() ??
        HttpResponse.json({
          success: true,
          items_created: 1,
          products_created: 1,
          aliases_learned: 1,
          error: null,
        })
      )
    }),
    http.post(`${API_URL}/receipts/r1/process`, () => {
      current = { ...current, processing_status: 'queued', error: null }
      return HttpResponse.json(current, { status: 202 })
    })
  )
  return confirms
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ReceiptReviewPage params={{ id: 'r1' }} />
      </ToastProvider>
    </QueryClientProvider>
  )
}

const addButton = () => screen.getByRole('button', { name: /^add \d+ items?$/i })
const dismissButton = () => screen.getByRole('button', { name: /^dismiss receipt$/i })
const showHousehold = () => fireEvent.click(screen.getByRole('button', { name: 'Show' }))
const rows = () => screen.getAllByRole('listitem')

describe('ReceiptReviewPage', () => {
  it('prefills each row from the read line', async () => {
    mockApi(receipt())
    renderPage()

    expect(await screen.findByText(/S-group/)).toBeInTheDocument()
    expect(screen.getByText(finnishDaysAgo(3), { exact: false })).toBeInTheDocument()
    expect(screen.getByLabelText('Product name')).toHaveValue('Generic 0')
    expect(screen.getByText('PRINTED 0')).toBeInTheDocument()
    // Presence, not amounts (V2): the row names the thing; the amount goes along unseen
    expect(screen.queryByLabelText('Quantity')).not.toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Unit' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Category')).toHaveValue('dairy')
    expect(addButton()).toBeEnabled()
  })

  it('sends matched lines by product and new lines by name', async () => {
    const confirms = mockApi(
      receipt({}, [
        item(0, { product_id: 'p-milk', product_name: 'Milk', match_confidence: 'exact' }),
        item(1),
      ])
    )
    renderPage()

    await screen.findByText('→ Milk')
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    // line_id addresses the line by identity (H12); index stays for one release.
    expect(confirms[0]).toEqual({
      non_food_indexes: [],
      items: [
        { index: 0, line_id: 'line-0', product_id: 'p-milk', quantity: 1, unit: 'pcs', purchase_date: isoDaysAgo(3) },
        { index: 1, line_id: 'line-1', name: 'Generic 1', category: 'dairy', quantity: 1, unit: 'pcs', purchase_date: isoDaysAgo(3) },
      ],
    })
    expect(await screen.findByText(/Added 1 item/)).toBeInTheDocument()
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'))
  })

  it('excludes a line with no category until one is chosen', async () => {
    const confirms = mockApi(
      receipt({}, [item(0), item(1, { suggested_category: null, generic_name: 'Trash bag' })])
    )
    renderPage()

    await screen.findByText('PRINTED 1')
    const [, second] = rows()
    expect(within(second).getByRole('checkbox')).not.toBeChecked()
    expect(within(second).getByText(/pick a category to include/i)).toBeInTheDocument()
    expect(addButton()).toHaveAccessibleName(/add 1 item$/i)

    fireEvent.change(within(second).getByLabelText('Category'), { target: { value: 'meat' } })

    expect(within(second).getByRole('checkbox')).toBeChecked()
    fireEvent.click(addButton())
    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items).toHaveLength(2)
  })

  it('skips a line that is toggled off and counts it', async () => {
    const confirms = mockApi(receipt({}, [item(0), item(1)]))
    renderPage()

    await screen.findByText('PRINTED 1')
    fireEvent.click(within(rows()[1]).getByRole('checkbox'))

    expect(screen.getByText(/1 skipped/i)).toBeInTheDocument()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: { index: number }[] }).items.map((i) => i.index)).toEqual([0])
  })

  it('sends the edited name with the amount the receipt read', async () => {
    const confirms = mockApi(receipt())
    renderPage()

    await screen.findByLabelText('Product name')
    fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Oat drink' } })
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[0]).toMatchObject({
      name: 'Oat drink',
      quantity: 1,
      unit: 'pcs',
    })
  })

  it('falls back to today when the receipt has no date', async () => {
    const confirms = mockApi(receipt({ purchase_date: null }))
    renderPage()

    await screen.findByLabelText('Product name')
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    const sent = (confirms[0] as { items: { purchase_date: string }[] }).items[0]
    expect(sent.purchase_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('keeps the page and shows the API message when confirm fails', async () => {
    mockApi(receipt(), () =>
      HttpResponse.json({ detail: 'Receipt already confirmed' }, { status: 409 })
    )
    renderPage()

    await screen.findByLabelText('Product name')
    fireEvent.click(addButton())

    expect(await screen.findByText('Receipt already confirmed')).toBeInTheDocument()
    expect(push).not.toHaveBeenCalled()
  })

  it('shows progress while the receipt is still being read', async () => {
    mockApi(receipt({ processing_status: 'processing', items: [] }, []))
    renderPage()

    expect(await screen.findByText(/still reading this receipt/i)).toBeInTheDocument()
  })

  it('offers to read a failed receipt again', async () => {
    mockApi(receipt({ processing_status: 'failed', error: 'LLM timed out', items: [] }, []))
    renderPage()

    expect(await screen.findByText('LLM timed out')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /read again/i }))

    // Re-queued: the page switches to the reading state and polls
    expect(await screen.findByText(/still reading this receipt/i)).toBeInTheDocument()
  })

  it('shows a confirmed receipt read-only', async () => {
    mockApi(receipt({ processing_status: 'confirmed' }))
    renderPage()

    expect(await screen.findByText(/already added to your stock/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^add/i })).not.toBeInTheDocument()
    // Q9: confirming used to drop the read method, and this is the screen you come back
    // to when the stock looks wrong.
    expect(screen.getByText(/It was read by the model\./)).toBeInTheDocument()
  })

  it('keeps saying a confirmed receipt was read without the model (Q9)', async () => {
    mockApi(receipt({ processing_status: 'confirmed', extraction_method: 'heuristic' }))
    renderPage()

    expect(
      await screen.findByText(/read without the model, so names are as printed/i)
    ).toBeInTheDocument()
  })

  // The status chain had no final branch, so anything outside the handled set fell through to
  // the review form and rendered an empty list with an "Add 0 items" button (H04).
  it('says so when the receipt is in a status it does not know', async () => {
    mockApi(receipt({ processing_status: 'archived', items: [] }, []))
    renderPage()

    expect(await screen.findByText(/state this app does not know: archived/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^add \d+ items?$/i })).not.toBeInTheDocument()
  })

  it('offers to read a pre-queue receipt that was never read', async () => {
    // 'uploaded' predates MVP-R3; such a row has no items and nothing to review
    mockApi(receipt({ processing_status: 'uploaded', items: [] }, []))
    renderPage()

    expect(await screen.findByText(/never queued to be read/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /read it now/i }))

    expect(await screen.findByText(/still reading this receipt/i)).toBeInTheDocument()
  })

  it('notes a receipt read without the model', async () => {
    mockApi(receipt({ extraction_method: 'heuristic', fallback_reason: 'Model unavailable' }))
    renderPage()

    expect(await screen.findByText(/read without the AI model/i)).toBeInTheDocument()
  })

  it('says a good read was a good read, instead of saying nothing (Q9)', async () => {
    // Silence used to mean both "the model read it" and "the model never ran".
    mockApi(receipt({ extraction_method: 'text' }))
    renderPage()

    expect(await screen.findByText('read by the model')).toBeInTheDocument()
  })

  it('warns that an old receipt adds items already expired (Q10)', async () => {
    // Expiry is purchase_date + shelf life, counted from the shop. That is right, and it
    // means a receipt from months ago quietly adds a shelf of expired food. Dates are
    // relative to today so this test does not rot.
    mockApi(receipt({ purchase_date: isoDaysAgo(102) }))
    renderPage()

    const warning = await screen.findByRole('alert')
    expect(warning).toHaveTextContent(/expiry dates are counted from then/i)
    expect(warning.textContent).toContain(finnishDaysAgo(102))
  })

  it('says nothing about a receipt from this week', async () => {
    mockApi(receipt({ purchase_date: isoDaysAgo(3) }))
    renderPage()

    await screen.findByLabelText('Product name')
    expect(screen.queryByText(/counted from then/i)).not.toBeInTheDocument()
  })

  it('cannot warn when the date was never read', async () => {
    mockApi(receipt({ purchase_date: null }))
    renderPage()

    await screen.findByLabelText('Product name')
    expect(screen.queryByText(/counted from then/i)).not.toBeInTheDocument()
  })

  it('keeps a weighed line counted into pieces, without showing either', async () => {
    // Q2: the shop sold 1.072 kg of apples; the cook eats them one at a time. The backend still
    // counts them; the screen no longer says so (V2, presence not amounts)
    const confirms = mockApi(
      receipt({}, [
        item(0, {
          name: 'KG OMENA GOLDEN',
          generic_name: 'Apple',
          quantity: 9,
          unit: 'pcs',
          piece_grams: 125,
          printed_quantity: 1072,
          printed_unit: 'g',
        }),
      ])
    )
    renderPage()

    await screen.findByLabelText('Product name')
    expect(screen.queryByText(/→/)).not.toBeInTheDocument()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[0]).toMatchObject({
      quantity: 9,
      unit: 'pcs',
    })
  })

  it('adds a line read as nothing as one, since there is no amount to fix on screen', async () => {
    const confirms = mockApi(receipt({}, [item(0, { quantity: 0, unit: 'pcs' })]))
    renderPage()

    await screen.findByLabelText('Product name')
    expect(addButton()).toBeEnabled()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[0]).toMatchObject({ quantity: 1 })
  })

  it('keeps a counted line weighed into grams, without showing either', async () => {
    // Q8, the mirror: the shop sold 1 pack of mince; the backend keeps the 400 g
    const confirms = mockApi(
      receipt({}, [
        item(0, {
          name: 'SIKA-NAUTAJAUHELIHA 23%',
          generic_name: 'Ground beef',
          quantity: 400,
          unit: 'g',
          pack_grams: 400,
          printed_quantity: 1,
          printed_unit: 'pcs',
        }),
      ])
    )
    renderPage()

    await screen.findByLabelText('Product name')
    expect(screen.queryByText(/→/)).not.toBeInTheDocument()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[0]).toMatchObject({
      quantity: 400,
      unit: 'g',
    })
  })

  it('folds household lines away instead of listing them', async () => {
    // Q1: nine dead rows to scroll past every week is the friction
    mockApi(
      receipt({}, [
        item(0),
        item(1, {
          name: 'KOMPOSTOINTIPUSSI PAPERI',
          generic_name: 'Compost bag',
          suggested_category: null,
          non_food: true,
        }),
      ])
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(rows()).toHaveLength(1)
    expect(screen.getByText(/1 household item · Compost bag/)).toBeInTheDocument()
  })

  it('shows household lines again on request', async () => {
    mockApi(
      receipt({}, [
        item(0),
        item(1, { generic_name: 'Compost bag', suggested_category: null, non_food: true }),
      ])
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))

    expect(rows()).toHaveLength(2)
  })

  it('remembers the household lines the cook has looked at', async () => {
    // Opening the fold is what makes this a judgement rather than the model's
    // guess; see the test below (H08).
    const confirms = mockApi(
      receipt({}, [
        item(0),
        item(1, { generic_name: 'Compost bag', suggested_category: null, non_food: true }),
      ])
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    showHousehold()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect(confirms[0].non_food_indexes).toEqual([1])
    expect((confirms[0] as { items: { index: number }[] }).items.map((i) => i.index)).toEqual([0])
  })

  it('a household line the cook puts back is not remembered', async () => {
    const confirms = mockApi(
      receipt({}, [
        item(0),
        item(1, { generic_name: 'Compost bag', suggested_category: null, non_food: true }),
      ])
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    showHousehold()
    // Giving it a category is how the cook says "this one really is food"
    fireEvent.change(within(rows()[1]).getByLabelText('Category'), {
      target: { value: 'dairy' },
    })
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect(confirms[0].non_food_indexes).toEqual([])
    expect((confirms[0] as { items: { index: number }[] }).items).toHaveLength(2)
  })

  it('a household fold the cook never opened teaches nothing', async () => {
    // The model's guess alone is not a judgement. Remembering it would hide a real
    // food line from every future receipt, and nothing could unlearn it (H08).
    const confirms = mockApi(
      receipt({}, [
        item(0),
        item(1, { generic_name: 'Compost bag', suggested_category: null, non_food: true }),
      ])
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect(confirms[0].non_food_indexes).toEqual([])
  })

  it('a receipt with nothing to add can be dismissed', async () => {
    // An all-household receipt, a duplicate, or a read that found no lines. Before
    // H08 Confirm was disabled at zero items, so the receipt stayed `completed` and
    // the home banner counted it as waiting forever.
    const confirms = mockApi(
      receipt({}, [
        item(0, { generic_name: 'Compost bag', suggested_category: null, non_food: true }),
      ])
    )
    renderPage()

    await waitFor(() => expect(dismissButton()).toBeEnabled())
    fireEvent.click(dismissButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items).toEqual([])
  })

  it('shows a confirmed mapping as known and a proposal as auto', async () => {
    // The row used to print `match_confidence`, and because the pipeline only kept
    // matches scoring 80 or better, every guess read "high" - including the ones that
    // paired Pineapple with Apple (H15).
    mockApi(
      receipt({}, [
        item(0, {
          product_id: 'p-milk',
          product_name: 'Milk',
          match_source: 'alias',
          verified: true,
        }),
        item(1, {
          product_id: 'p-oat',
          product_name: 'Oat drink',
          match_source: 'selected',
          verified: false,
        }),
      ])
    )
    renderPage()

    await screen.findByText('→ Milk')
    expect(within(rows()[0]).getByText('known')).toBeInTheDocument()
    expect(within(rows()[1]).getByText('auto')).toBeInTheDocument()
  })

  it('lets the cook change a proposed product, and sends the one they chose', async () => {
    const confirms = mockApi(
      receipt({}, [
        item(0, {
          product_id: 'p-oat',
          product_name: 'Oat drink',
          match_source: 'selected',
          verified: false,
        }),
      ])
    )
    renderPage()

    await screen.findByText('→ Oat drink')
    fireEvent.click(screen.getByRole('button', { name: 'Change Oat drink' }))
    search('Milk', `row-0-search`)
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))

    await screen.findByText('→ Milk')
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    const [sent] = (confirms[0] as { items: { product_id?: string }[] }).items
    expect(sent.product_id).toBe('p-milk')
  })

  it('a changed row reads as the cook own word, not a proposal', async () => {
    mockApi(
      receipt({}, [
        item(0, {
          product_id: 'p-oat',
          product_name: 'Oat drink',
          match_source: 'selected',
          verified: false,
        }),
      ])
    )
    renderPage()

    await screen.findByText('→ Oat drink')
    expect(screen.getByText('auto')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Change Oat drink' }))
    search('Milk', `row-0-search`)
    fireEvent.click(await screen.findByRole('button', { name: 'Milk' }))

    await screen.findByText('→ Milk')
    expect(screen.getByText('known')).toBeInTheDocument()
  })

  it('lets the cook detach a proposal and name a new product instead', async () => {
    const confirms = mockApi(
      receipt({}, [
        item(0, {
          product_id: 'p-oat',
          product_name: 'Oat drink',
          match_source: 'selected',
          verified: false,
          suggested_category: 'dairy',
        }),
      ])
    )
    renderPage()

    await screen.findByText('→ Oat drink')
    fireEvent.click(screen.getByRole('button', { name: 'Change Oat drink' }))
    search('Barista oat', `row-0-search`)
    fireEvent.click(await screen.findByRole('button', { name: 'New product: Barista oat' }))

    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    const [sent] = (confirms[0] as { items: Record<string, unknown>[] }).items
    expect(sent.product_id).toBeUndefined()
    expect(sent.name).toBe('Barista oat')
  })

  it('renders and confirms a long receipt', async () => {
    const many = Array.from({ length: 50 }, (_, index) => item(index))
    const confirms = mockApi(receipt({}, many))
    renderPage()

    await screen.findByText('PRINTED 49')
    expect(rows()).toHaveLength(50)
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items).toHaveLength(50)
  })
})

describe('ReceiptReviewPage completeness (Q27)', () => {
  // The K-Citymarket receipt as the backend reports it (contract ruling 1): 15 product rows in
  // the end, the model's first read returned 6, the targeted re-read put back the other 9, and
  // after recovery every amount-bearing line is accounted for.
  const K_RECEIPT: NonNullable<Receipt['completeness']> = {
    text_lines: 15,
    model_lines: 6,
    recovered_by_retry: 9,
    recovered_raw_lines: 0,
    unaccounted_lines: 0,
    invalid_entries: 0,
    items_sum: 73.07,
    receipt_total: 73.07,
  }

  function kReceipt(completeness = K_RECEIPT): Receipt {
    const read = Array.from({ length: 6 }, (_, index) => item(index))
    const recovered = Array.from({ length: 9 }, (_, n) =>
      item(6 + n, { recovered: 'model_retry' })
    )
    return receipt({ completeness }, [...read, ...recovered])
  }

  it('says how many lines the model missed and marks the recovered ones', async () => {
    mockApi(kReceipt())
    renderPage()

    await screen.findByText('PRINTED 14')
    expect(
      screen.getByText(
        '9 of 15 lines were not read by the model — they are recovered below, please check them.'
      )
    ).toBeInTheDocument()
    expect(screen.getAllByText('recovered')).toHaveLength(9)
    expect(within(rows()[6]).getByText('recovered')).toBeInTheDocument()
    expect(within(rows()[5]).queryByText('recovered')).not.toBeInTheDocument()
    // The header counts every row, recovered ones included
    expect(screen.getByText('15 items read, 0 already known')).toBeInTheDocument()
    expect(screen.queryByText(/unusable entries/)).not.toBeInTheDocument()
    // The sum agrees with the total and every line was accounted for after recovery
    expect(screen.queryByText(/add up to/)).not.toBeInTheDocument()
    expect(screen.queryByText(/could not be read/)).not.toBeInTheDocument()
  })

  it('says how many lines are still unread after recovery', async () => {
    mockApi(kReceipt({ ...K_RECEIPT, unaccounted_lines: 1 }))
    renderPage()

    await screen.findByText('PRINTED 14')
    expect(screen.getByText(/^9 of 15 lines were not read by the model/)).toBeInTheDocument()
    expect(
      screen.getByText('1 line could not be read — see the receipt text.')
    ).toBeInTheDocument()
  })

  it('says nothing is missing when the fallback parser read the receipt', async () => {
    // The model failed; the fallback read all 15 rows and says so in its own note
    const rowsRead = Array.from({ length: 15 }, (_, index) => item(index))
    mockApi(
      receipt(
        {
          extraction_method: 'heuristic',
          completeness: {
            ...K_RECEIPT,
            model_lines: 0,
            recovered_by_retry: 0,
            recovered_raw_lines: 0,
            unaccounted_lines: 0,
          },
        },
        rowsRead
      )
    )
    renderPage()

    await screen.findByText('PRINTED 14')
    expect(screen.getByText(/Read without the AI model/)).toBeInTheDocument()
    expect(screen.queryByText(/could not be read/)).not.toBeInTheDocument()
    expect(screen.queryByText(/not read by the model/)).not.toBeInTheDocument()
  })

  it('says the items do not add up to the receipt total', async () => {
    mockApi(
      receipt({
        completeness: {
          ...K_RECEIPT,
          text_lines: null,
          model_lines: 1,
          recovered_by_retry: 0,
          items_sum: 30,
          receipt_total: 42.1,
        },
      })
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(
      screen.getByText(
        'The items add up to 30.00 but the receipt total is 42.10 — something may be missing.'
      )
    ).toBeInTheDocument()
    // A photo receipt has no text lines to count
    expect(screen.queryByText(/not read by the model/)).not.toBeInTheDocument()
  })

  it.each([
    ['within 1% of the total', 99.5, 100],
    ['exactly five cents apart', 0.95, 1.0],
    ['within five cents on a small total', 3.1, 3.14],
  ])('lets a rounding difference pass: %s', async (_, itemsSum, receiptTotal) => {
    mockApi(
      receipt({
        completeness: {
          ...K_RECEIPT,
          recovered_by_retry: 0,
          items_sum: itemsSum,
          receipt_total: receiptTotal,
        },
      })
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(screen.queryByText(/add up to/)).not.toBeInTheDocument()
  })

  it('flags a difference of six cents', async () => {
    mockApi(
      receipt({
        completeness: { ...K_RECEIPT, recovered_by_retry: 0, items_sum: 0.94, receipt_total: 1.0 },
      })
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(screen.getByText(/add up to 0.94 but the receipt total is 1.00/)).toBeInTheDocument()
  })

  it('shows no banner when nothing was recovered', async () => {
    mockApi(
      receipt({
        completeness: { ...K_RECEIPT, text_lines: 1, model_lines: 1, recovered_by_retry: 0 },
      })
    )
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(screen.queryByText(/not read by the model/)).not.toBeInTheDocument()
    expect(screen.queryByText('recovered')).not.toBeInTheDocument()
  })

  it('shows no banner for an older receipt without completeness', async () => {
    mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(screen.queryByText(/not read by the model/)).not.toBeInTheDocument()
  })

  it('treats the nulls the API sends like an older receipt', async () => {
    const confirms = mockApi(receipt({ completeness: null }, [item(0, { recovered: null })]))
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(screen.queryByText(/not read by the model/)).not.toBeInTheDocument()
    expect(screen.queryByText('recovered')).not.toBeInTheDocument()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items).toHaveLength(1)
  })

  it('says nothing about unusable entries when nothing else is wrong', async () => {
    mockApi(receipt({ completeness: { ...K_RECEIPT, recovered_by_retry: 0, invalid_entries: 2 } }))
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(screen.queryByText(/unusable entries/)).not.toBeInTheDocument()
  })

  it('counts both kinds of recovery and mentions unusable entries', async () => {
    mockApi(
      kReceipt({
        ...K_RECEIPT,
        recovered_by_retry: 7,
        recovered_raw_lines: 2,
        invalid_entries: 3,
      })
    )
    renderPage()

    await screen.findByText('PRINTED 14')
    expect(screen.getByText(/^9 of 15 lines were not read by the model/)).toBeInTheDocument()
    expect(screen.getByText("The model's answer had 3 unusable entries.")).toBeInTheDocument()
  })

  it('words a single recovered line in the singular', async () => {
    mockApi(
      receipt(
        { completeness: { ...K_RECEIPT, text_lines: 2, model_lines: 1, recovered_by_retry: 1 } },
        [item(0), item(1, { recovered: 'model_retry' })]
      )
    )
    renderPage()

    await screen.findByText('PRINTED 1')
    expect(
      screen.getByText(
        '1 of 2 lines was not read by the model — it is recovered below, please check it.'
      )
    ).toBeInTheDocument()
  })

  it('leaves out "of N" when there is no text to count lines in', async () => {
    mockApi(
      receipt(
        { completeness: { ...K_RECEIPT, text_lines: null, model_lines: 1, recovered_by_retry: 1 } },
        [item(0), item(1, { recovered: 'model_retry' })]
      )
    )
    renderPage()

    await screen.findByText('PRINTED 1')
    expect(
      screen.getByText('1 line was not read by the model — it is recovered below, please check it.')
    ).toBeInTheDocument()
  })

  it('opens the household fold when a recovered line is in it', async () => {
    const confirms = mockApi(
      receipt(
        { completeness: { ...K_RECEIPT, text_lines: 2, model_lines: 1, recovered_by_retry: 1 } },
        [
          item(0),
          item(1, {
            generic_name: 'Detergent',
            suggested_category: null,
            non_food: true,
            recovered: 'model_retry',
          }),
        ]
      )
    )
    renderPage()

    await screen.findByText('PRINTED 1')
    // The banner says "recovered below", so the row has to be there to check
    expect(rows()).toHaveLength(2)
    expect(within(rows()[1]).getByText('recovered')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide' })).toBeInTheDocument()
    fireEvent.click(addButton())

    // Shown, so it counts as seen and its non-food judgement is taught (H08)
    await waitFor(() => expect(confirms).toHaveLength(1))
    expect(confirms[0].non_food_indexes).toEqual([1])
  })

  it('a line taken from the receipt text starts skipped until it has a category', async () => {
    const confirms = mockApi(
      receipt(
        {
          completeness: {
            ...K_RECEIPT,
            text_lines: 2,
            model_lines: 1,
            recovered_by_retry: 0,
            recovered_raw_lines: 1,
          },
        },
        [
          item(0),
          item(1, {
            name: 'KG BANAANI',
            generic_name: null,
            suggested_category: null,
            recovered: 'raw_line',
          }),
        ]
      )
    )
    renderPage()

    await screen.findByText('KG BANAANI')
    const [first, second] = rows()
    expect(within(second).getByText('recovered')).toBeInTheDocument()
    expect(
      within(second).getByText('from the receipt text — pick a category')
    ).toBeInTheDocument()
    expect(within(first).queryByText(/from the receipt text/)).not.toBeInTheDocument()
    expect(within(second).getByRole('checkbox')).not.toBeChecked()
    expect(addButton()).toHaveAccessibleName(/add 1 item$/i)

    fireEvent.change(within(second).getByLabelText('Category'), { target: { value: 'meat' } })
    expect(within(second).getByRole('checkbox')).toBeChecked()
    // Once it has a category there is nothing left to ask for
    expect(within(second).getByText('from the receipt text')).toBeInTheDocument()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[1]).toEqual({
      index: 1,
      line_id: 'line-1',
      name: 'KG BANAANI',
      category: 'meat',
      quantity: 1,
      unit: 'pcs',
      purchase_date: isoDaysAgo(3),
    })
  })

  it('does not ask for a category on a raw line that matched a product', async () => {
    mockApi(
      receipt({}, [
        item(0, {
          name: 'KG BANAANI',
          generic_name: null,
          suggested_category: null,
          product_id: 'p-milk',
          product_name: 'Milk',
          match_source: 'alias',
          recovered: 'raw_line',
        }),
      ])
    )
    renderPage()

    await screen.findByText('→ Milk')
    expect(screen.getByText('from the receipt text')).toBeInTheDocument()
    expect(screen.queryByText(/pick a category/)).not.toBeInTheDocument()
  })
})

describe('ReceiptReviewPage missed items (Q27)', () => {
  const addToList = () => screen.getByRole('button', { name: 'Add to list' })

  function fillMissed(name: string, category = 'dairy', quantity = '2', unit = 'dl') {
    fireEvent.change(screen.getByLabelText('Missed item name'), { target: { value: name } })
    fireEvent.change(screen.getByLabelText('Missed item category'), {
      target: { value: category },
    })
    fireEvent.change(screen.getByLabelText('Missed item amount'), {
      target: { value: quantity },
    })
    const unitGroup = screen.getByRole('radiogroup', { name: 'Missed item unit' })
    fireEvent.click(within(unitGroup).getByLabelText(unit))
  }

  it('labels its fields with real labels', async () => {
    mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    const name = screen.getByLabelText('Missed item name')
    expect(document.querySelector(`label[for="${name.id}"]`)).toHaveTextContent('Missed item name')
    // The read rows' own fields still resolve to exactly one element each
    expect(screen.getByLabelText('Category')).toHaveValue('dairy')
    expect(screen.getByLabelText('Product name')).toHaveValue('Generic 0')
  })

  it('sends a hand-added item as a free line', async () => {
    const confirms = mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    fillMissed('Cream')
    fireEvent.click(addToList())

    expect(screen.getByText('Cream')).toBeInTheDocument()
    // The form is ready for the next one
    expect(screen.getByLabelText('Missed item name')).toHaveValue('')
    expect(addButton()).toHaveAccessibleName(/add 2 items$/i)
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect(confirms[0]).toEqual({
      non_food_indexes: [],
      items: [
        { index: 0, line_id: 'line-0', name: 'Generic 0', category: 'dairy', quantity: 1, unit: 'pcs', purchase_date: isoDaysAgo(3) },
        { name: 'Cream', category: 'dairy', quantity: 2, unit: 'dl', purchase_date: isoDaysAgo(3) },
      ],
    })
  })

  it('takes a decimal comma in the amount', async () => {
    const confirms = mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    fillMissed('Cream', 'dairy', '1,5')
    expect(addToList()).toBeEnabled()
    fireEvent.click(addToList())
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[1]).toMatchObject({
      name: 'Cream',
      quantity: 1.5,
      unit: 'dl',
    })
  })

  it('cannot add an item without a name', async () => {
    mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    fillMissed('   ')
    expect(addToList()).toBeDisabled()
    fireEvent.click(addToList())
    expect(addButton()).toHaveAccessibleName(/add 1 item$/i)
  })

  it('cannot add an item without a category', async () => {
    mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    fillMissed('Cream', '')
    expect(addToList()).toBeDisabled()
  })

  it.each(['0', '-1', 'abc'])('cannot add an item with an amount of %s', async (amount) => {
    mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    fillMissed('Cream', 'dairy', amount)
    expect(addToList()).toBeDisabled()
  })

  it('drops a hand-added item that is removed before confirming', async () => {
    const confirms = mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    fillMissed('Cream')
    fireEvent.click(addToList())
    fillMissed('Butter', 'dairy', '1', 'pcs')
    fireEvent.click(addToList())
    fireEvent.click(screen.getByRole('button', { name: 'Remove Cream' }))

    expect(screen.queryByText('Cream')).not.toBeInTheDocument()
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    const sent = (confirms[0] as { items: Record<string, unknown>[] }).items
    expect(sent).toHaveLength(2)
    expect(sent[1]).toEqual({
      name: 'Butter',
      category: 'dairy',
      quantity: 1,
      unit: 'pcs',
      purchase_date: isoDaysAgo(3),
    })
  })

  it('a receipt with only a hand-added item confirms it rather than dismissing', async () => {
    const confirms = mockApi(receipt({}, []))
    renderPage()

    await screen.findByRole('button', { name: /^dismiss receipt$/i })
    fillMissed('Cream')
    fireEvent.click(addToList())
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items).toHaveLength(1)
  })

  it('includes a filled-in item the cook did not add to the list', async () => {
    // Tapping the footer instead of "Add to list" must not lose what was typed
    const confirms = mockApi(receipt())
    renderPage()

    await screen.findByText('PRINTED 0')
    fillMissed('Cream')
    expect(addButton()).toHaveAccessibleName(/add 2 items$/i)
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[1]).toEqual({
      name: 'Cream',
      category: 'dairy',
      quantity: 2,
      unit: 'dl',
      purchase_date: isoDaysAgo(3),
    })
  })

  it('a filled-in item turns "Dismiss receipt" into adding it', async () => {
    const confirms = mockApi(receipt({}, []))
    renderPage()

    await screen.findByRole('button', { name: /^dismiss receipt$/i })
    fillMissed('Cream')
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items).toHaveLength(1)
  })

  it('will not confirm while a started item is incomplete', async () => {
    const confirms = mockApi(receipt({}, []))
    renderPage()

    await screen.findByRole('button', { name: /^dismiss receipt$/i })
    fillMissed('Cream', '')
    fireEvent.click(dismissButton())

    expect(
      await screen.findByText('Finish the missed item or clear its name before confirming')
    ).toBeInTheDocument()
    expect(confirms).toHaveLength(0)
    expect(push).not.toHaveBeenCalled()
  })
})

describe('ReceiptReviewPage receipt text (Q28)', () => {
  it('keeps the receipt text folded until asked for', async () => {
    mockApi(receipt({ ocr_raw_text: 'K-CITYMARKET\nKG BANAANI 1,20' }))
    renderPage()

    const toggle = await screen.findByRole('button', { name: 'Show receipt text' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    // The region exists while collapsed so aria-controls resolves, but is hidden
    const region = document.getElementById(toggle.getAttribute('aria-controls') ?? '')
    expect(region).not.toBeNull()
    expect(region).not.toBeVisible()

    fireEvent.click(toggle)

    expect(screen.getByText(/KG BANAANI 1,20/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Hide receipt text' })).toHaveAttribute(
      'aria-expanded',
      'true'
    )
  })

  it('offers no receipt text when there is none', async () => {
    mockApi(receipt({ ocr_raw_text: null }))
    renderPage()

    await screen.findByText('PRINTED 0')
    expect(screen.queryByRole('button', { name: /receipt text/i })).not.toBeInTheDocument()
  })
})
