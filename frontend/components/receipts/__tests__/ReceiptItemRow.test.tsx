/**
 * ReceiptItemRow: the printed line is always visible (Q39), and a per-row "Re-analyse"
 * with an optional hint re-asks the model for that line alone (Q38).
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { ReceiptItemRow, type ReviewRow } from '../ReceiptItemRow'
import type { Category } from '@/types/category'
import type { ExtractedItem } from '@/types/receipt'

const CATEGORIES: Category[] = [
  {
    id: 'dairy',
    display_name: 'Dairy & Eggs',
    icon: '🥛',
    default_shelf_life_days: 7,
    frozen_shelf_life_days: null,
    sort_order: 20,
    default_storage: 'refrigerator',
    shelf_life_min_days: 1,
    shelf_life_max_days: 30,
  },
]

function item(overrides: Partial<ExtractedItem> = {}): ExtractedItem {
  return {
    index: 0,
    line_id: 'line-0',
    name: 'PESTO JA CASHEW',
    generic_name: 'Dip',
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

function row(overrides: Partial<ReviewRow> = {}): ReviewRow {
  return {
    index: 0,
    include: true,
    name: 'Dip',
    category: 'dairy',
    quantity: '1',
    unit: 'pcs',
    ...overrides,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function tree(
  queryClient: QueryClient,
  onChange: (changes: Partial<ReviewRow>) => void,
  onReanalysed: (item: ExtractedItem) => void,
  props: Partial<React.ComponentProps<typeof ReceiptItemRow>>
) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ReceiptItemRow
          item={item()}
          row={row()}
          categories={CATEGORIES}
          receiptId="r1"
          dirty={false}
          onChange={onChange}
          onReanalysed={onReanalysed}
          {...props}
        />
      </ToastProvider>
    </QueryClientProvider>
  )
}

function renderRow(props: Partial<React.ComponentProps<typeof ReceiptItemRow>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const onChange = jest.fn()
  const onReanalysed = jest.fn()
  const { rerender } = render(tree(queryClient, onChange, onReanalysed, props))
  return {
    onChange,
    onReanalysed,
    // Re-renders the same tree (same QueryClient, same component instance) with new
    // props - for simulating a prop change, such as `dirty` flipping, while a mutation
    // from the first render is still in flight.
    rerenderWith: (next: Partial<React.ComponentProps<typeof ReceiptItemRow>>) =>
      rerender(tree(queryClient, onChange, onReanalysed, { ...props, ...next })),
  }
}

describe('printed line (Q39)', () => {
  it('shows the printed line and its price', () => {
    renderRow({ item: item({ price: 2.49 }) })

    expect(screen.getByText('PESTO JA CASHEW · 2.49')).toBeInTheDocument()
  })

  it('shows the printed line with no price when none is stored', () => {
    renderRow({ item: item({ price: null }) })

    expect(screen.getByText('PESTO JA CASHEW')).toBeInTheDocument()
  })

  it('shows it whether or not the row is matched to a product', () => {
    renderRow({
      item: item({ product_id: 'p1', product_name: 'Cashew nuts', price: 2.49 }),
    })

    expect(screen.getByText('PESTO JA CASHEW · 2.49')).toBeInTheDocument()
    expect(screen.getByText('→ Cashew nuts')).toBeInTheDocument()
  })

  it('never lets the generic name field replace the printed line', () => {
    renderRow({ row: row({ name: 'Something the cook typed' }) })

    expect(screen.getByLabelText('Product name')).toHaveValue('Something the cook typed')
    expect(screen.getByText('PESTO JA CASHEW')).toBeInTheDocument()
  })
})

describe('re-analyse (Q38)', () => {
  it('offers no re-analyse control for a line with no stable id', () => {
    renderRow({ item: item({ line_id: null }) })

    expect(screen.queryByRole('button', { name: 'Re-analyse' })).not.toBeInTheDocument()
  })

  it('reveals the hint field only once opened', () => {
    renderRow()

    expect(screen.queryByPlaceholderText(/what is it/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Re-analyse' }))

    expect(screen.getByPlaceholderText(/what is it/i)).toBeInTheDocument()
  })

  it('sends the hint and reports the answer', async () => {
    let body: unknown
    server.use(
      http.post(`${API_URL}/receipts/r1/lines/line-0/reanalyse`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json(item({ generic_name: 'Cashew nuts' }))
      })
    )
    const { onReanalysed } = renderRow()

    fireEvent.click(screen.getByRole('button', { name: 'Re-analyse' }))
    fireEvent.change(screen.getByPlaceholderText(/what is it/i), {
      target: { value: 'cashew nuts' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask again' }))

    await waitFor(() => expect(onReanalysed).toHaveBeenCalled())
    expect(body).toEqual({ hint: 'cashew nuts' })
    expect(onReanalysed.mock.calls[0][0].generic_name).toBe('Cashew nuts')
  })

  it('asks before applying the result when the row is dirty', async () => {
    server.use(
      http.post(`${API_URL}/receipts/r1/lines/line-0/reanalyse`, () =>
        HttpResponse.json(item({ generic_name: 'Model name' }))
      )
    )
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(false)
    const { onReanalysed } = renderRow({ dirty: true })

    fireEvent.click(screen.getByRole('button', { name: 'Re-analyse' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask again' }))

    await waitFor(() => expect(confirmSpy).toHaveBeenCalled())
    expect(onReanalysed).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('reads dirty at response time, not click time (F3)', async () => {
    let resolve!: (value: Response) => void
    const pending = new Promise<Response>((r) => {
      resolve = r
    })
    server.use(
      http.post(`${API_URL}/receipts/r1/lines/line-0/reanalyse`, () => pending)
    )
    const confirmSpy = jest.spyOn(window, 'confirm').mockReturnValue(true)
    const { onReanalysed, rerenderWith } = renderRow({ dirty: false })

    // Clicked while the row was clean: a closure over `dirty` at click time would
    // never ask, however the row changes afterwards.
    fireEvent.click(screen.getByRole('button', { name: 'Re-analyse' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask again' }))

    // The cook edits the row while the request is still in flight.
    rerenderWith({ dirty: true })

    resolve(HttpResponse.json(item({ generic_name: 'Model name' })))

    await waitFor(() => expect(confirmSpy).toHaveBeenCalled())
    expect(onReanalysed).toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('shows a toast with the error message and leaves the row unchanged', async () => {
    server.use(
      http.post(`${API_URL}/receipts/r1/lines/line-0/reanalyse`, () =>
        HttpResponse.json({ detail: 'The model did not answer in time' }, { status: 504 })
      )
    )
    const { onReanalysed } = renderRow()

    fireEvent.click(screen.getByRole('button', { name: 'Re-analyse' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask again' }))

    expect(
      await screen.findByText('The model did not answer in time')
    ).toBeInTheDocument()
    expect(onReanalysed).not.toHaveBeenCalled()
  })
})
