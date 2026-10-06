import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { LANGUAGE_KEY } from '@/lib/language'
import { GenerateSheet } from '../GenerateSheet'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderSheet(onClose = jest.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <GenerateSheet open onClose={onClose} />
      </ToastProvider>
    </QueryClientProvider>
  )
  return onClose
}

/** The two generate calls the sheet makes: the dry run, then the applied run. */
function api(dryRunBody: Record<string, unknown>, appliedBody?: Record<string, unknown>) {
  const asked: Array<{ dry_run: boolean }> = []
  server.use(
    http.post(`${API_URL}/shopping/generate`, async ({ request }) => {
      const body = (await request.json()) as { dry_run: boolean }
      asked.push(body)
      return HttpResponse.json(body.dry_run ? dryRunBody : (appliedBody ?? dryRunBody))
    })
  )
  return asked
}

describe('GenerateSheet', () => {
  it('previews before writing anything', async () => {
    const asked = api({
      added: [{ product_id: 'p1', name: 'Milk', need: 4, unit: 'dl', on_hand: 1, min_stock: 5, item_id: null, reason: null }],
      updated: [],
      unchanged: [],
      skipped: [],
      dry_run: true,
    })

    renderSheet()

    expect(await screen.findByText(/Milk/)).toBeInTheDocument()
    expect(asked).toEqual([{ sources: ['low_stock', 'runout'], dry_run: true }])
  })

  it('applies on "Add to list", using the same sources', async () => {
    const onClose = jest.fn()
    const asked = api(
      {
        added: [{ product_id: 'p1', name: 'Milk', need: 4, unit: 'dl', on_hand: 1, min_stock: 5, item_id: null, reason: null }],
        updated: [],
        unchanged: [],
        skipped: [],
        dry_run: true,
      },
      {
        added: [{ product_id: 'p1', name: 'Milk', need: 4, unit: 'dl', on_hand: 1, min_stock: 5, item_id: 'i1', reason: null }],
        updated: [],
        unchanged: [],
        skipped: [],
        dry_run: false,
      }
    )
    renderSheet(onClose)
    await screen.findByText(/Milk/)

    fireEvent.click(screen.getByRole('button', { name: 'Add to list' }))

    await waitFor(() => expect(asked).toHaveLength(2))
    expect(asked[1]).toEqual({ sources: ['low_stock', 'runout'], dry_run: false })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('sends a fresh Idempotency-Key on apply, and reuses it on a retry (F1)', async () => {
    let attempts = 0
    const headers: Array<string | null> = []
    server.use(
      http.post(`${API_URL}/shopping/generate`, async ({ request }) => {
        const body = (await request.json()) as { dry_run: boolean }
        if (body.dry_run) {
          return HttpResponse.json({
            added: [
              {
                product_id: 'p1',
                name: 'Milk',
                need: 4,
                unit: 'dl',
                on_hand: 1,
                min_stock: 5,
                item_id: null,
                reason: null,
              },
            ],
            updated: [],
            unchanged: [],
            skipped: [],
            dry_run: true,
          })
        }
        attempts += 1
        headers.push(request.headers.get('Idempotency-Key'))
        if (attempts === 1) {
          return HttpResponse.json({ detail: 'boom' }, { status: 500 })
        }
        return HttpResponse.json({
          added: [],
          updated: [],
          unchanged: [],
          skipped: [],
          dry_run: false,
        })
      })
    )
    renderSheet()
    await screen.findByText(/Milk/)

    fireEvent.click(screen.getByRole('button', { name: 'Add to list' }))
    expect(await screen.findByText('Could not generate the list')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add to list' }))
    await waitFor(() => expect(attempts).toBe(2))

    expect(headers[0]).toBeTruthy()
    expect(headers[0]).toBe(headers[1])
  })

  it('disables "Add to list" when nothing is short', async () => {
    api({ added: [], updated: [], unchanged: [], skipped: [], dry_run: true })

    renderSheet()

    expect(await screen.findByText(/Nothing is short/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add to list' })).toBeDisabled()
  })

  it('shows why a product was skipped', async () => {
    api({
      added: [],
      updated: [],
      unchanged: [],
      skipped: [
        {
          product_id: 'p2',
          name: 'Flour',
          need: null,
          unit: 'g',
          on_hand: null,
          min_stock: 500,
          item_id: null,
          reason: 'stock in tsp cannot be counted against min_stock in g',
        },
      ],
      dry_run: true,
    })

    renderSheet()

    expect(await screen.findByText(/Flour/)).toBeInTheDocument()
    expect(screen.getByText(/cannot be counted/)).toBeInTheDocument()
  })

  describe('sources (CL6: running out soon)', () => {
    const empty = { added: [], updated: [], unchanged: [], skipped: [], dry_run: true }

    it('offers both sources, on by default', async () => {
      api(empty)

      renderSheet()

      expect(screen.getByRole('checkbox', { name: 'Low stock' })).toBeChecked()
      expect(screen.getByRole('checkbox', { name: 'Running out soon' })).toBeChecked()
    })

    it('sends only the source left on, for the preview and the apply', async () => {
      const asked = api({
        added: [{ product_id: 'p1', name: 'Milk', need: 4, unit: 'dl', on_hand: 1, min_stock: 5, item_id: null, reason: null }],
        updated: [],
        unchanged: [],
        skipped: [],
        dry_run: true,
      })
      renderSheet()
      await screen.findByText(/Milk/)

      fireEvent.click(screen.getByRole('checkbox', { name: 'Running out soon' }))

      await waitFor(() => expect(asked).toHaveLength(2))
      expect(asked[1]).toEqual({ sources: ['low_stock'], dry_run: true })
      await screen.findByText(/Milk/)
      fireEvent.click(screen.getByRole('button', { name: 'Add to list' }))
      await waitFor(() => expect(asked).toHaveLength(3))
      expect(asked[2]).toEqual({ sources: ['low_stock'], dry_run: false })
    })

    it('cannot submit with no source on', async () => {
      const asked = api({
        added: [{ product_id: 'p1', name: 'Milk', need: 4, unit: 'dl', on_hand: 1, min_stock: 5, item_id: null, reason: null }],
        updated: [],
        unchanged: [],
        skipped: [],
        dry_run: true,
      })
      renderSheet()
      await screen.findByText(/Milk/)

      fireEvent.click(screen.getByRole('checkbox', { name: 'Low stock' }))
      await waitFor(() => expect(asked).toHaveLength(2))
      await screen.findByText(/Milk/)
      fireEvent.click(screen.getByRole('checkbox', { name: 'Running out soon' }))

      expect(await screen.findByText('Choose at least one source.')).toBeInTheDocument()
      const add = screen.getByRole('button', { name: 'Add to list' })
      expect(add).toBeDisabled()
      fireEvent.click(add)
      expect(asked).toHaveLength(2)
      expect(asked.every((body) => body.dry_run)).toBe(true)
    })

    it('dates a line the run-out forecast picked', async () => {
      api({
        added: [
          {
            product_id: 'p1',
            name: 'Milk',
            need: 9,
            unit: 'dl',
            on_hand: 3,
            min_stock: 0,
            item_id: null,
            reason: 'runs out around 2026-10-12 at 1.25 dl a day',
            runs_out_on: '2026-10-12',
          },
        ],
        updated: [],
        unchanged: [],
        skipped: [],
        dry_run: true,
      })

      renderSheet()

      expect(await screen.findByText('Milk · 9 dl · runs out ~12 October 2026')).toBeInTheDocument()
    })

    it('reads the sources and the date in Finnish', async () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      api({
        added: [],
        updated: [
          {
            product_id: 'p1',
            name: 'Maito',
            need: 9,
            unit: 'dl',
            on_hand: 3,
            min_stock: 0,
            item_id: 'i1',
            reason: 'runs out around 2026-10-12 at 1.25 dl a day',
            runs_out_on: '2026-10-12',
          },
        ],
        unchanged: [],
        skipped: [],
        dry_run: true,
      })

      renderSheet()

      expect(screen.getByRole('checkbox', { name: 'Vähissä' })).toBeChecked()
      expect(screen.getByRole('checkbox', { name: 'Loppumassa pian' })).toBeChecked()
      expect(
        await screen.findByText('Maito · 9 dl · loppuu ~12. lokakuuta 2026')
      ).toBeInTheDocument()
      window.localStorage.clear()
    })
  })

  describe('display language (Post-MVP frontier item 13, phase 2)', () => {
    afterEach(() => window.localStorage.clear())

    it('reads the sheet in Finnish, and a decimal need with a comma', async () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      api({
        added: [
          { product_id: 'p1', name: 'Milk', need: 2.5, unit: 'dl', on_hand: 1, min_stock: 5, item_id: null, reason: null },
        ],
        updated: [],
        unchanged: [],
        skipped: [],
        dry_run: true,
      })

      renderSheet()

      expect(screen.getByRole('heading', { name: 'Luo ostoslista' })).toBeInTheDocument()
      // Waits for the dry run itself, not just the title (which renders before it resolves)
      expect(await screen.findByText('Milk · 2,5 dl')).toBeInTheDocument()
      expect(screen.getByText('Uudet')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Lisää listalle' })).toBeInTheDocument()
    })
  })
})
