/**
 * Receipt audit view (Q28): the original file, the OCR text, the model's raw answer and each
 * printed line's outcome, reachable for any receipt - confirmed included.
 */

import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import ReceiptAuditPage from '../page'
import type { ReceiptAudit } from '@/types/receipt'

function audit(overrides: Partial<ReceiptAudit> = {}): ReceiptAudit {
  return {
    id: 'r1',
    store_chain: 's-group',
    purchase_date: '2026-09-26',
    processing_status: 'confirmed',
    created_at: '2026-09-26T10:00:00Z',
    ocr_raw_text: null,
    model_raw_answer: null,
    model_raw_answer_retry: null,
    file_content_type: 'image/jpeg',
    lines: [],
    unlinked_items: [],
    ...overrides,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage(data: ReceiptAudit) {
  server.use(http.get(`${API_URL}/receipts/r1/audit`, () => HttpResponse.json(data)))
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ReceiptAuditPage params={{ id: 'r1' }} />
    </QueryClientProvider>
  )
}

describe('ReceiptAuditPage', () => {
  it('names the store and date, and shows the status', async () => {
    renderPage(audit())

    expect(await screen.findByText('S-group, 26.9.2026')).toBeInTheDocument()
    expect(screen.getByText('Added to stock')).toBeInTheDocument()
  })

  it('shows the original image', async () => {
    renderPage(audit({ file_content_type: 'image/jpeg' }))

    const img = await screen.findByAltText('The scanned receipt')
    expect(img).toHaveAttribute('src', expect.stringContaining('/receipts/r1/file'))
  })

  it('offers a PDF in an object element with an open link', async () => {
    renderPage(audit({ file_content_type: 'application/pdf' }))

    const link = await screen.findByRole('link', { name: 'Open the original' })
    expect(link).toHaveAttribute('href', expect.stringContaining('/receipts/r1/file'))
  })

  it('says so when the original file is gone', async () => {
    renderPage(audit({ file_content_type: null }))

    expect(
      await screen.findByText('The original file is no longer available.')
    ).toBeInTheDocument()
  })

  it('shows each line with its outcome', async () => {
    renderPage(
      audit({
        lines: [
          { index: 0, name: 'VALIO MAITO 1L', price: 1.49, outcome: 'stocked', items: [
            { id: 'item-1', product_id: 'prod-1', product_name: 'Milk' },
          ] },
          { index: 1, name: 'MUOVIKASSI', price: 0.1, outcome: 'household', items: [] },
          { index: 2, name: 'PIRKKA HERNEET', price: 0.99, outcome: 'skipped', items: [] },
        ],
      })
    )

    expect(await screen.findByText('VALIO MAITO 1L')).toBeInTheDocument()
    expect(screen.getByText('Stocked')).toBeInTheDocument()
    expect(screen.getByText('Household')).toBeInTheDocument()
    expect(screen.getByText('Skipped')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Milk' })).toHaveAttribute('href', '/products')
  })

  it('lists items created before the line index existed, unattributed', async () => {
    renderPage(
      audit({
        unlinked_items: [{ id: 'legacy-1', product_id: 'prod-2', product_name: 'Butter' }],
      })
    )

    expect(
      await screen.findByText('Also created from this receipt (line unknown)')
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Butter' })).toBeInTheDocument()
  })

  it('keeps the OCR text and the model answer folded until asked for, as plain text', async () => {
    renderPage(
      audit({
        ocr_raw_text: '<b>MAITO</b> 1,49',
        model_raw_answer: '{"lines": []}',
      })
    )

    const ocrToggle = await screen.findByRole('button', { name: 'Show OCR text' })
    expect(ocrToggle).toHaveAttribute('aria-expanded', 'false')
    const answerToggle = screen.getByRole('button', { name: "Show Model's answer" })

    fireEvent.click(ocrToggle)
    fireEvent.click(answerToggle)

    // Rendered as text, not parsed: the tag shows up literally rather than becoming markup
    expect(screen.getByText('<b>MAITO</b> 1,49')).toBeInTheDocument()
    expect(document.querySelector('b')).not.toBeInTheDocument()
    expect(screen.getByText('{"lines": []}')).toBeInTheDocument()
  })

  it('offers a second block for the targeted re-read, when one was stored (Q27)', async () => {
    renderPage(audit({ model_raw_answer_retry: '{"lines": [{"n": "MISSED"}]}' }))

    const toggle = await screen.findByRole('button', { name: "Show Model's answer (retry)" })
    fireEvent.click(toggle)

    expect(screen.getByText('{"lines": [{"n": "MISSED"}]}')).toBeInTheDocument()
  })

  it('offers no retry block when no retry ran', async () => {
    renderPage(audit({ model_raw_answer_retry: null }))

    await screen.findByText('S-group, 26.9.2026')
    expect(
      screen.queryByRole('button', { name: /retry/i })
    ).not.toBeInTheDocument()
  })

  it('offers neither text block when neither was stored', async () => {
    renderPage(audit({ ocr_raw_text: null, model_raw_answer: null }))

    await screen.findByText('S-group, 26.9.2026')
    expect(screen.queryByRole('button', { name: /OCR text/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /answer/ })).not.toBeInTheDocument()
  })

  it('links back to the review screen for a receipt not yet confirmed', async () => {
    renderPage(audit({ processing_status: 'completed' }))

    expect(
      await screen.findByRole('link', { name: 'Go to the review screen' })
    ).toHaveAttribute('href', '/receipt/r1')
  })

  it('offers no review-screen link for a confirmed receipt', async () => {
    renderPage(audit({ processing_status: 'confirmed' }))

    await screen.findByText('S-group, 26.9.2026')
    expect(
      screen.queryByRole('link', { name: 'Go to the review screen' })
    ).not.toBeInTheDocument()
  })

  it('says when a receipt cannot be found', async () => {
    server.use(
      http.get(`${API_URL}/receipts/missing/audit`, () =>
        HttpResponse.json({ detail: 'not found' }, { status: 404 })
      )
    )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <ReceiptAuditPage params={{ id: 'missing' }} />
      </QueryClientProvider>
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Receipt not found.')
  })
})
