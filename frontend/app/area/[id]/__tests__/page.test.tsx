/**
 * An area's grid (V4): the tiles of one part of the fridge, stalest first, no numbers. A tap
 * uses an item up; "…" opens its sheet.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import AreaPage from '../page'
import type { InventoryItem } from '@/types/inventory'

function inDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

const item = (overrides: Partial<InventoryItem>): InventoryItem => ({
  id: 'item-x',
  product_master_id: 'p1',
  product_name: 'X',
  category: 'meat',
  category_name: 'Meat & Poultry',
  category_icon: '🥩',
  receipt_id: null,
  initial_quantity: 400,
  current_quantity: 400,
  unit: 'g',
  status: 'sealed',
  purchase_date: '2026-09-20',
  expiry_date: inDays(20),
  expiry_source: 'calculated',
  opened_date: null,
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2026-09-20T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
  ...overrides,
})

const STEAK = item({ id: 'item-steak', product_name: 'Steak', expiry_date: inDays(10) })
const MINCE = item({ id: 'item-mince', product_name: 'Minced Meat', expiry_date: inDays(1) })
const MILK = item({
  id: 'item-milk',
  product_name: 'Oat Milk',
  category: 'dairy',
  category_icon: '🥛',
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderArea(id: string, stock: () => InventoryItem[], ...handlers: Parameters<typeof server.use>) {
  server.use(
    ...handlers,
    http.get(`${API_URL}/inventory`, () => HttpResponse.json(stock())),
    http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null))
  )
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AreaPage params={{ id }} />
      </ToastProvider>
    </QueryClientProvider>
  )
}

const grid = () => screen.getByRole('list', { name: /Meat & fish/ })

describe('an area', () => {
  it('shows only its own tiles, stalest first', async () => {
    renderArea('meat', () => [STEAK, MILK, MINCE])

    await screen.findByRole('button', { name: 'Steak, keeps' })
    const names = within(grid())
      .getAllByRole('button', { name: /, / })
      .map((button) => button.getAttribute('aria-label'))
    expect(names).toEqual(['Minced Meat, going stale', 'Steak, keeps'])
  })

  it('shows no numbers', async () => {
    const { container } = renderArea('meat', () => [STEAK, MINCE])

    await screen.findByRole('button', { name: 'Steak, keeps' })
    expect(container.querySelector('main')?.textContent).not.toMatch(/\d/)
  })

  it('uses an item up with one tap', async () => {
    let stock = [STEAK]
    const bodies: unknown[] = []
    renderArea(
      'meat',
      () => stock,
      http.post(`${API_URL}/inventory/item-steak/consume`, async ({ request }) => {
        bodies.push(await request.json())
        stock = []
        return HttpResponse.json({ ...STEAK, current_quantity: 0, status: 'empty' })
      })
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Steak, keeps' }))

    await waitFor(() => expect(bodies).toEqual([{ quantity: 400 }]))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Steak, keeps' })).not.toBeInTheDocument()
    )
  })

  it('opens an item\'s sheet from its "…"', async () => {
    renderArea('meat', () => [STEAK])

    fireEvent.click(await screen.findByRole('button', { name: 'More for Steak' }))

    expect(await screen.findByRole('dialog', { name: 'Steak' })).toBeInTheDocument()
  })

  it('says so when it is empty', async () => {
    renderArea('meat', () => [MILK])

    expect(await screen.findByText(/Nothing here/)).toBeInTheDocument()
  })

  it('leads back to the fridge', async () => {
    renderArea('meat', () => [])

    expect(await screen.findByRole('link', { name: /Fridge/ })).toHaveAttribute('href', '/')
  })

  it('says so for an area that does not exist', () => {
    renderArea('garage', () => [])

    expect(screen.getByText('No such part of the fridge.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Fridge/ })).toHaveAttribute('href', '/')
  })
})
