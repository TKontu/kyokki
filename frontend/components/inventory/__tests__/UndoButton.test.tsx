/**
 * One general undo in the header (operator, 2026-09-22): the most recent change to stock,
 * whichever item and whoever made it, and again for the one before.
 */

import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server, API_URL } from '@/test/msw/server'
import { ToastProvider } from '@/components/ui/Toast'
import { UndoButton } from '../UndoButton'
import type { UndoPreview } from '@/types/consumption'

const APPLE: UndoPreview = {
  batch_id: 'batch-apple',
  logged_at: '2026-09-22T08:00:00+00:00',
  steps: [
    {
      inventory_item_id: 'i1',
      product_name: 'Apples',
      unit: 'pcs',
      action: 'use_partial',
      quantity_consumed: 1,
    },
  ],
}

const MILK: UndoPreview = {
  ...APPLE,
  batch_id: 'batch-milk',
  steps: [{ ...APPLE.steps[0], product_name: 'Milk', action: 'discard' }],
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderButton() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <UndoButton />
      </ToastProvider>
    </QueryClientProvider>
  )
}

describe('UndoButton', () => {
  it('is there but disabled when there is nothing to undo', async () => {
    server.use(http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(null)))

    renderButton()

    const button = await screen.findByRole('button', { name: /undo/i })
    await waitFor(() => expect(button).toBeDisabled())
  })

  it('says what it will undo', async () => {
    server.use(http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(APPLE)))

    renderButton()

    expect(
      await screen.findByRole('button', { name: 'Undo Used some · Apples' })
    ).toBeEnabled()
  })

  it('undoes exactly what it showed, then offers the step before', async () => {
    const sent: unknown[] = []
    let next: UndoPreview | null = APPLE
    server.use(
      http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(next)),
      http.post(`${API_URL}/inventory/undo`, async ({ request }) => {
        sent.push(await request.json())
        next = MILK
        return HttpResponse.json({ undone: 1 })
      })
    )
    renderButton()

    fireEvent.click(await screen.findByRole('button', { name: 'Undo Used some · Apples' }))

    expect(
      await screen.findByRole('button', { name: 'Undo Thrown away · Milk' })
    ).toBeInTheDocument()
    expect(sent).toEqual([{ batch_id: 'batch-apple' }])
  })

  it('says so when something newer got there first, and shows the newer thing', async () => {
    let next: UndoPreview = APPLE
    server.use(
      http.get(`${API_URL}/inventory/undo`, () => HttpResponse.json(next)),
      http.post(`${API_URL}/inventory/undo`, () => {
        next = MILK
        return HttpResponse.json(
          { detail: 'Something newer has happened since; nothing was undone' },
          { status: 409 }
        )
      })
    )
    renderButton()

    fireEvent.click(await screen.findByRole('button', { name: 'Undo Used some · Apples' }))

    expect(
      await screen.findByText('Something newer has happened since; nothing was undone')
    ).toBeInTheDocument()
    expect(
      await screen.findByRole('button', { name: 'Undo Thrown away · Milk' })
    ).toBeInTheDocument()
  })
})
