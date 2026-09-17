/**
 * Receipt review page (MVP-R7): edit the read lines, skip what you do not want, confirm.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import ReceiptReviewPage from '../page'
import type { ExtractedItem, Receipt, ReceiptStatus } from '@/types/receipt'

const push = jest.fn()
jest.mock('next/navigation', () => ({ useRouter: () => ({ push, back: jest.fn() }) }))

const CATEGORIES = [
  { id: 'dairy', display_name: 'Dairy & Eggs', icon: '🥛', default_shelf_life_days: 7, meal_contexts: null, sort_order: 20, default_storage: 'refrigerator' },
  { id: 'meat', display_name: 'Meat & Poultry', icon: '🥩', default_shelf_life_days: 5, meal_contexts: null, sort_order: 10, default_storage: 'refrigerator' },
]

function item(index: number, overrides: Partial<ExtractedItem> = {}): ExtractedItem {
  return {
    index,
    name: `PRINTED ${index}`,
    generic_name: `Generic ${index}`,
    quantity: 1,
    unit: 'pcs',
    product_id: null,
    product_name: null,
    match_score: null,
    match_confidence: null,
    match_source: null,
    suggested_category: 'dairy',
    piece_grams: null,
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

function receipt(overrides: Partial<Receipt> = {}, items: ExtractedItem[] = [item(0)]): Receipt {
  return {
    id: 'r1',
    store_chain: 's-group',
    purchase_date: '2026-09-02',
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

function mockApi(body: Receipt, confirmResponse?: () => Response) {
  const confirms: Record<string, unknown>[] = []
  // The fake keeps state like the API does: re-queueing changes what a refetch returns
  let current = body
  server.use(
    http.get(`${API_URL}/categories`, () => HttpResponse.json(CATEGORIES)),
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
const rows = () => screen.getAllByRole('listitem')

describe('ReceiptReviewPage', () => {
  it('prefills each row from the read line', async () => {
    mockApi(receipt())
    renderPage()

    expect(await screen.findByText(/S-group/)).toBeInTheDocument()
    expect(screen.getByText(/2\.9\.2026/)).toBeInTheDocument()
    expect(screen.getByLabelText('Product name')).toHaveValue('Generic 0')
    expect(screen.getByText('PRINTED 0')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toHaveValue(1)
    expect(screen.getByRole('radio', { name: 'pcs' })).toBeChecked()
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
    expect(confirms[0]).toEqual({
      non_food_indexes: [],
      items: [
        { index: 0, product_id: 'p-milk', quantity: 1, unit: 'pcs', purchase_date: '2026-09-02' },
        { index: 1, name: 'Generic 1', category: 'dairy', quantity: 1, unit: 'pcs', purchase_date: '2026-09-02' },
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

  it('sends edited name, quantity and unit', async () => {
    const confirms = mockApi(receipt())
    renderPage()

    await screen.findByLabelText('Product name')
    fireEvent.change(screen.getByLabelText('Product name'), { target: { value: 'Oat drink' } })
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '10' } })
    fireEvent.click(screen.getByText('dl'))
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect((confirms[0] as { items: unknown[] }).items[0]).toMatchObject({
      name: 'Oat drink',
      quantity: 10,
      unit: 'dl',
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
  })

  it('notes a receipt read without the model', async () => {
    mockApi(receipt({ extraction_method: 'heuristic', fallback_reason: 'Model unavailable' }))
    renderPage()

    expect(await screen.findByText(/read without the AI model/i)).toBeInTheDocument()
  })

  it('shows what the receipt weighed when it was counted into pieces', async () => {
    // Q2: the shop sold 1.072 kg of apples; the cook eats them one at a time
    mockApi(
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

    expect(await screen.findByText(/1\.072 kg → 9 pcs/)).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toHaveValue(9)
    expect(screen.getByRole('radio', { name: 'pcs' })).toBeChecked()
  })

  it('says nothing about a conversion that did not happen', async () => {
    mockApi(receipt({}, [item(0, { quantity: 400, unit: 'g' })]))
    renderPage()

    await screen.findByLabelText('Quantity')
    expect(screen.queryByText(/→/)).not.toBeInTheDocument()
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

  it('remembers the household lines when confirming', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    // Giving it a category is how the cook says "this one really is food"
    fireEvent.change(within(rows()[1]).getByLabelText('Category'), {
      target: { value: 'dairy' },
    })
    fireEvent.click(addButton())

    await waitFor(() => expect(confirms).toHaveLength(1))
    expect(confirms[0].non_food_indexes).toEqual([])
    expect((confirms[0] as { items: { index: number }[] }).items).toHaveLength(2)
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
