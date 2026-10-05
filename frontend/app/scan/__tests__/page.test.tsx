/**
 * Scan page (MVP-R6): upload a receipt from the iPad and hand over to the review screen.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import ScanPage from '../page'

const push = jest.fn()
let mockSearch = ''
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push, back: jest.fn() }),
  useSearchParams: () => new URLSearchParams(mockSearch),
}))

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  server.resetHandlers()
  push.mockReset()
  mockSearch = ''
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

function choose(...files: File[]) {
  const input = screen.getByLabelText('Receipt') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
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

describe('ScanPage: several receipts at once (Post-MVP frontier item 8)', () => {
  /** Answer each upload in turn from `answers`, recording the order the files arrived in. */
  function mockScanSequence(answers: Array<() => Response>) {
    const names: string[] = []
    const uploads: FormData[] = []
    server.use(
      http.post(`${API_URL}/receipts/scan`, async ({ request }) => {
        const form = await request.formData()
        uploads.push(form)
        names.push((form.get('file') as File).name)
        return answers[names.length - 1]()
      })
    )
    return { names, uploads }
  }

  const created = (id: string) => () =>
    HttpResponse.json({ id, processing_status: 'queued' }, { status: 201 })

  it('lets the cook pick several files', () => {
    renderPage()

    expect(screen.getByLabelText('Receipt')).toHaveAttribute('multiple')
  })

  it('names how many receipts the button will upload', () => {
    renderPage()

    choose(pdf('a.pdf'), pdf('b.pdf'), pdf('c.pdf'))

    expect(screen.getByRole('button', { name: 'Upload 3 receipts' })).toBeEnabled()
    expect(screen.getByText(/apply to every file/i)).toBeInTheDocument()
  })

  it('uploads each file in order and then opens the receipt list', async () => {
    const { names } = mockScanSequence([created('r-1'), created('r-2')])
    renderPage()

    choose(pdf('first.pdf'), pdf('second.pdf'))
    fireEvent.click(uploadButton())

    await waitFor(() => expect(push).toHaveBeenCalledWith('/receipts'))
    expect(names).toEqual(['first.pdf', 'second.pdf'])
    expect(push).toHaveBeenCalledTimes(1)
  })

  it('counts a receipt that is already here as done, not as a failure', async () => {
    mockScanSequence([
      created('r-1'),
      () =>
        HttpResponse.json(
          { detail: { message: 'Receipt already uploaded', receipt_id: 'r-existing' } },
          { status: 409 }
        ),
    ])
    renderPage()

    choose(pdf('first.pdf'), pdf('second.pdf'))
    fireEvent.click(uploadButton())

    await waitFor(() => expect(push).toHaveBeenCalledWith('/receipts'))
  })

  it('keeps going past a failed file and shows what happened to each', async () => {
    const { names } = mockScanSequence([
      created('r-1'),
      () => HttpResponse.json({ detail: 'Unsupported file type: text/plain' }, { status: 400 }),
    ])
    renderPage()

    choose(pdf('first.pdf'), pdf('notes.txt'))
    fireEvent.click(uploadButton())

    const results = await screen.findByRole('list', { name: /results/i })
    expect(names).toEqual(['first.pdf', 'notes.txt'])
    expect(push).not.toHaveBeenCalled()
    const rows = within(results).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('first.pdf')
    expect(within(rows[0]).getByRole('link')).toHaveAttribute('href', '/receipt/r-1')
    expect(rows[1]).toHaveTextContent('notes.txt')
    expect(rows[1]).toHaveTextContent('Unsupported file type: text/plain')
    expect(within(rows[1]).queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /all receipts/i })).toHaveAttribute(
      'href',
      '/receipts'
    )
  })

  it('does not stop when the first file fails', async () => {
    const { names } = mockScanSequence([
      () => HttpResponse.error(),
      created('r-2'),
    ])
    renderPage()

    choose(pdf('first.pdf'), pdf('second.pdf'))
    fireEvent.click(uploadButton())

    const results = await screen.findByRole('list', { name: /results/i })
    expect(names).toEqual(['first.pdf', 'second.pdf'])
    const rows = within(results).getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent(/could not upload/i)
    expect(within(rows[1]).getByRole('link')).toHaveAttribute('href', '/receipt/r-2')
  })

  it('sends the store and date with every file', async () => {
    const { uploads } = mockScanSequence([created('r-1'), created('r-2')])
    renderPage()

    choose(pdf('first.pdf'), pdf('second.pdf'))
    fireEvent.change(screen.getByLabelText(/store/i), { target: { value: 'Lidl' } })
    fireEvent.change(screen.getByLabelText(/purchase date/i), {
      target: { value: '2026-09-02' },
    })
    fireEvent.click(uploadButton())

    await waitFor(() => expect(uploads).toHaveLength(2))
    for (const form of uploads) {
      expect(form.get('store_chain')).toBe('Lidl')
      expect(form.get('purchase_date')).toBe('2026-09-02')
    }
  })

  it('shows its progress and holds the button while uploading', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    // The second upload hangs until the test lets it through
    server.use(
      http.post(`${API_URL}/receipts/scan`, async ({ request }) => {
        const form = await request.formData()
        const name = (form.get('file') as File).name
        if (name === 'second.pdf') await gate
        return HttpResponse.json(
          { id: name === 'first.pdf' ? 'r-1' : 'r-2', processing_status: 'queued' },
          { status: 201 }
        )
      })
    )
    renderPage()

    choose(pdf('first.pdf'), pdf('second.pdf'), pdf('third.pdf'))
    fireEvent.click(uploadButton())

    expect(await screen.findByText('Uploading 2 of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload/i })).toBeDisabled()
    release()
    await waitFor(() => expect(push).toHaveBeenCalledWith('/receipts'))
  })
})

describe('ScanPage: files a share could not queue', () => {
  it('says the shared files could not be queued', () => {
    mockSearch = 'shared=failed'
    renderPage()

    expect(screen.getByRole('status')).toHaveTextContent(/could not be queued/i)
  })

  it('drops the note once the cook picks files here', () => {
    mockSearch = 'shared=failed'
    renderPage()

    choose(pdf())

    expect(screen.queryByText(/could not be queued/i)).not.toBeInTheDocument()
  })

  it('shows no note on a plain visit', () => {
    renderPage()

    expect(screen.queryByText(/could not be queued/i)).not.toBeInTheDocument()
  })
})

describe('ScanPage: display language (Post-MVP frontier item 13, phase 3)', () => {
  beforeEach(() => {
    window.localStorage.setItem('kyokki.language', 'fi')
  })
  afterEach(() => {
    window.localStorage.clear()
  })

  it('shows the form chrome in Finnish', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Skannaa kuitti' })).toBeInTheDocument()
    expect(screen.getByLabelText('Kuitti')).toBeInTheDocument()
    expect(screen.getByLabelText('Kauppa (valinnainen)')).toBeInTheDocument()
    expect(screen.getByLabelText('Ostopäivä (valinnainen)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Lähetä' })).toBeInTheDocument()
  })

  function chooseFi(file: File) {
    const input = screen.getByLabelText('Kuitti') as HTMLInputElement
    Object.defineProperty(input, 'files', { value: [file], configurable: true })
    fireEvent.change(input)
  }

  it('says why in Finnish when the file cannot be read', async () => {
    mockScan(() =>
      HttpResponse.json({ detail: 'Unsupported file type: text/plain' }, { status: 400 })
    )
    renderPage()

    chooseFi(pdf('notes.txt'))
    fireEvent.click(screen.getByRole('button', { name: 'Lähetä' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Unsupported file type: text/plain'
    )
  })

  it('says something useful in Finnish when the upload never lands', async () => {
    server.use(http.post(`${API_URL}/receipts/scan`, () => HttpResponse.error()))
    renderPage()

    chooseFi(pdf())
    fireEvent.click(screen.getByRole('button', { name: 'Lähetä' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Kuitin lähetys epäonnistui. Yritä uudelleen.'
    )
  })

  it('shows the several-file text in Finnish', async () => {
    mockSearch = 'shared=failed'
    server.use(
      http.post(`${API_URL}/receipts/scan`, async ({ request }) => {
        const form = await request.formData()
        return (form.get('file') as File).name === 'first.pdf'
          ? HttpResponse.json({ id: 'r-1', processing_status: 'queued' }, { status: 201 })
          : HttpResponse.error()
      })
    )
    renderPage()

    expect(screen.getByRole('status')).toHaveTextContent(
      'Jaettuja tiedostoja ei voitu lisätä jonoon'
    )
    const input = screen.getByLabelText('Kuitti') as HTMLInputElement
    Object.defineProperty(input, 'files', {
      value: [pdf('first.pdf'), pdf('second.pdf')],
      configurable: true,
    })
    fireEvent.change(input)
    expect(screen.getByText(/koskevat kaikkia tiedostoja/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Lähetä 2 kuittia' }))

    const results = await screen.findByRole('list', { name: 'Tulokset' })
    const rows = within(results).getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('Lähetetty')
    expect(rows[1]).toHaveTextContent('Kuitin lähetys epäonnistui. Yritä uudelleen.')
    expect(screen.getByRole('link', { name: 'Kaikki kuitit' })).toHaveAttribute(
      'href',
      '/receipts'
    )
  })
})
