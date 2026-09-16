/**
 * Scan page (MVP-R6): upload a receipt from the iPad and hand over to the review screen.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import ScanPage from '../page'

const push = jest.fn()
jest.mock('next/navigation', () => ({ useRouter: () => ({ push, back: jest.fn() }) }))

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  push.mockReset()
})
afterAll(() => server.close())

const pdf = (name = 'receipt.pdf') =>
  new File(['%PDF receipt bytes'], name, { type: 'application/pdf' })

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <ScanPage />
    </QueryClientProvider>
  )
}

const uploadButton = () => screen.getByRole('button', { name: /upload/i })

function choose(file: File) {
  const input = screen.getByLabelText('Receipt') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  fireEvent.change(input)
}

/** Record what the API was sent, and answer with whatever the test wants. */
function mockScan(respond?: () => Response) {
  const uploads: FormData[] = []
  server.use(
    http.post(`${API_URL}/receipts/scan`, async ({ request }) => {
      uploads.push(await request.formData())
      return (
        respond?.() ??
        HttpResponse.json({ id: 'r-new', processing_status: 'queued' }, { status: 201 })
      )
    })
  )
  return uploads
}

describe('ScanPage', () => {
  it('will not upload until a receipt is chosen', () => {
    renderPage()

    expect(uploadButton()).toBeDisabled()
  })

  it('uploads the file and opens the receipt it created', async () => {
    const uploads = mockScan()
    renderPage()

    choose(pdf())
    fireEvent.click(uploadButton())

    await waitFor(() => expect(uploads).toHaveLength(1))
    expect((uploads[0].get('file') as File).name).toBe('receipt.pdf')
    // The review page already shows the reading state and polls
    await waitFor(() => expect(push).toHaveBeenCalledWith('/receipt/r-new'))
  })

  it('sends the store and date when the cook filled them in', async () => {
    const uploads = mockScan()
    renderPage()

    choose(pdf())
    fireEvent.change(screen.getByLabelText(/store/i), { target: { value: 'Lidl' } })
    fireEvent.change(screen.getByLabelText(/purchase date/i), {
      target: { value: '2026-09-02' },
    })
    fireEvent.click(uploadButton())

    await waitFor(() => expect(uploads).toHaveLength(1))
    expect(uploads[0].get('store_chain')).toBe('Lidl')
    expect(uploads[0].get('purchase_date')).toBe('2026-09-02')
  })

  it('leaves the optional fields out when they are empty', async () => {
    const uploads = mockScan()
    renderPage()

    choose(pdf())
    fireEvent.click(uploadButton())

    await waitFor(() => expect(uploads).toHaveLength(1))
    expect(uploads[0].get('store_chain')).toBeNull()
    expect(uploads[0].get('purchase_date')).toBeNull()
  })

  it('keeps the page and says why when the file is not one we can read', async () => {
    mockScan(() =>
      HttpResponse.json({ detail: 'Unsupported file type: text/plain' }, { status: 400 })
    )
    renderPage()

    choose(pdf('notes.txt'))
    fireEvent.click(uploadButton())

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unsupported file type: text/plain'
    )
    expect(push).not.toHaveBeenCalled()
  })

  it('opens the receipt that is already here instead of complaining about a duplicate', async () => {
    mockScan(() =>
      HttpResponse.json(
        { detail: { message: 'Receipt already uploaded', receipt_id: 'r-existing' } },
        { status: 409 }
      )
    )
    renderPage()

    choose(pdf())
    fireEvent.click(uploadButton())

    await waitFor(() => expect(push).toHaveBeenCalledWith('/receipt/r-existing'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says something useful when the upload never lands', async () => {
    server.use(http.post(`${API_URL}/receipts/scan`, () => HttpResponse.error()))
    renderPage()

    choose(pdf())
    fireEvent.click(uploadButton())

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not upload/i)
    expect(push).not.toHaveBeenCalled()
  })
})
