/**
 * The item sheet behind a tile's "…" (V2, presence not amounts): the name, "Used up", and the
 * way to the edit sheet. No amounts, no fractions - a tile tap already uses an item up, and
 * the header's Undo takes a mis-tap back.
 */

import React from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { ConsumptionSheet } from '../ConsumptionSheet'
import { ToastProvider } from '@/components/ui/Toast'
import { APIError } from '@/lib/api/errors'
import type { InventoryItem } from '@/types/inventory'

jest.mock('@/hooks/useInventory')
import { useConsumeInventoryItem } from '@/hooks/useInventory'
const mockUseConsume = useConsumeInventoryItem as jest.Mock

const MILK: InventoryItem = {
  id: 'item-milk',
  product_master_id: 'prod-milk',
  product_name: 'Oat Milk',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: null,
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 750,
  unit: 'dl',
  status: 'opened',
  purchase_date: '2024-01-01',
  expiry_date: '2024-03-01',
  expiry_source: 'calculated',
  opened_date: '2024-01-05',
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2024-01-01T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
}

type MutateOptions = { onSuccess?: () => void; onError?: (error: unknown) => void }

let mutate: jest.Mock

beforeEach(() => {
  mutate = jest.fn()
  mockUseConsume.mockReturnValue({ mutate, isPending: false })
})

function renderSheet(item: InventoryItem | null, onClose = jest.fn(), onEdit?: () => void) {
  const { container } = render(
    <ToastProvider>
      <ConsumptionSheet item={item} open={item !== null} onClose={onClose} onEdit={onEdit} />
    </ToastProvider>
  )
  return { onClose, container }
}

function lastMutateOptions(): MutateOptions {
  return mutate.mock.calls[mutate.mock.calls.length - 1][1]
}

describe('ConsumptionSheet', () => {
  describe('Rendering', () => {
    it('renders nothing without an item', () => {
      renderSheet(null)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('names the item and shows no amounts', () => {
      renderSheet(MILK)

      const sheet = screen.getByRole('dialog', { name: 'Oat Milk' })
      expect(sheet.textContent).not.toMatch(/\d/)
      expect(screen.queryByRole('button', { name: /½|¼|¾/ })).not.toBeInTheDocument()
    })

    it('gives Used up its own full-width button', () => {
      renderSheet(MILK)
      expect(screen.getByRole('button', { name: 'Used up' })).toHaveAttribute('data-primary')
    })

    it('offers the edit sheet', () => {
      const onEdit = jest.fn()
      renderSheet(MILK, jest.fn(), onEdit)

      fireEvent.click(screen.getByRole('button', { name: 'Edit item' }))

      expect(onEdit).toHaveBeenCalledTimes(1)
    })
  })

  describe('Using it up', () => {
    it('uses up everything that is left and closes', () => {
      const { onClose } = renderSheet(MILK)

      fireEvent.click(screen.getByRole('button', { name: 'Used up' }))

      expect(mutate).toHaveBeenCalledWith(
        { id: 'item-milk', data: { quantity: 750 } },
        expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
      )
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('Feedback', () => {
    it('confirms with a toast', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: 'Used up' }))

      act(() => lastMutateOptions().onSuccess?.())

      expect(screen.getByRole('status')).toHaveTextContent('Used up · Oat Milk')
    })

    it('shows the API error message', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: 'Used up' }))

      act(() =>
        lastMutateOptions().onError?.(
          new APIError(409, 'UNKNOWN_ERROR', 'Oat Milk has been thrown away')
        )
      )

      expect(screen.getByRole('alert')).toHaveTextContent('Oat Milk has been thrown away')
    })

    it('hides server and network error text behind a readable message', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: 'Used up' }))

      act(() =>
        lastMutateOptions().onError?.(
          new APIError(500, 'UNKNOWN_ERROR', 'Internal Server Error')
        )
      )

      expect(screen.getByRole('alert')).toHaveTextContent('Could not update Oat Milk')
      expect(screen.getByRole('alert')).not.toHaveTextContent('Internal Server Error')
    })

    it('falls back to a generic error message', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: 'Used up' }))

      act(() => lastMutateOptions().onError?.(new Error('')))

      expect(screen.getByRole('alert')).toHaveTextContent('Could not update Oat Milk')
    })
  })
})
