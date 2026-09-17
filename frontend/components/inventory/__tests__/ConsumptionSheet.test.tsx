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
}

const EGGS: InventoryItem = {
  ...MILK,
  id: 'item-eggs',
  product_name: 'Eggs',
  unit: 'pcs',
  initial_quantity: 10,
  current_quantity: 6,
}

type MutateOptions = { onSuccess?: () => void; onError?: (error: unknown) => void }

let mutate: jest.Mock

beforeEach(() => {
  mutate = jest.fn()
  mockUseConsume.mockReturnValue({ mutate, isPending: false })
})

function renderSheet(item: InventoryItem | null, onClose = jest.fn()) {
  render(
    <ToastProvider>
      <ConsumptionSheet item={item} open={item !== null} onClose={onClose} />
    </ToastProvider>
  )
  return onClose
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

    it('shows the product name and what is left', () => {
      renderSheet(MILK)
      expect(screen.getByRole('dialog', { name: 'Oat Milk' })).toBeInTheDocument()
      expect(screen.getByText('750 / 1000 dl left')).toBeInTheDocument()
    })

    it('offers fractions labelled with the amount for measured items', () => {
      renderSheet(MILK)
      // ¾ of 1000 is 750, which is everything left, so it is offered as Done instead
      for (const label of ['¼ · 250 dl', '½ · 500 dl', 'Done']) {
        expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
      }
    })

    it('leads with eating one for pieces', () => {
      renderSheet(EGGS)
      for (const label of ['1', '2', '3', 'All 6']) {
        expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
      }
      expect(screen.queryByRole('button', { name: /·/ })).not.toBeInTheDocument()
    })

    it('gives the common act its own full-width button', () => {
      renderSheet(EGGS)
      expect(screen.getByRole('button', { name: '1' }).className).toContain('w-full')
    })

    it('uses 56pt consumption buttons', () => {
      renderSheet(MILK)
      expect(
        screen.getByRole('button', { name: '½ · 500 dl' }).className
      ).toContain('min-h-touch-lg')
    })
  })

  describe('Consuming', () => {
    it('consumes half of the initial quantity and closes', () => {
      const onClose = renderSheet(MILK)

      fireEvent.click(screen.getByRole('button', { name: '½ · 500 dl' }))

      expect(mutate).toHaveBeenCalledWith(
        { id: 'item-milk', data: { quantity: 500 } },
        expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
      )
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('consumes everything that is left on Done', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: 'Done' }))
      expect(mutate.mock.calls[0][0]).toEqual({ id: 'item-milk', data: { quantity: 750 } })
    })

    it('consumes whole pieces', () => {
      renderSheet(EGGS)
      fireEvent.click(screen.getByRole('button', { name: '2' }))
      expect(mutate.mock.calls[0][0]).toEqual({ id: 'item-eggs', data: { quantity: 2 } })
    })
  })

  describe('Feedback', () => {
    it('confirms a fraction with a success toast', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: '½ · 500 dl' }))

      act(() => lastMutateOptions().onSuccess?.())

      expect(screen.getByRole('status')).toHaveTextContent('Consumed 500 dl · Oat Milk')
    })

    it('confirms Done as used up', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: 'Done' }))

      act(() => lastMutateOptions().onSuccess?.())

      expect(screen.getByRole('status')).toHaveTextContent('Used up · Oat Milk')
    })

    it('confirms pieces with the count', () => {
      renderSheet(EGGS)
      fireEvent.click(screen.getByRole('button', { name: '2' }))

      act(() => lastMutateOptions().onSuccess?.())

      expect(screen.getByRole('status')).toHaveTextContent('Consumed 2 pcs · Eggs')
    })

    it('shows the API error message', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: '½ · 500 dl' }))

      act(() =>
        lastMutateOptions().onError?.(
          new APIError(400, 'UNKNOWN_ERROR', 'Cannot consume 500 - only 100 available')
        )
      )

      expect(screen.getByRole('alert')).toHaveTextContent('Cannot consume 500 - only 100 available')
    })

    it('hides server and network error text behind a readable message', () => {
      renderSheet(MILK)
      fireEvent.click(screen.getByRole('button', { name: '½ · 500 dl' }))

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
      fireEvent.click(screen.getByRole('button', { name: '½ · 500 dl' }))

      act(() => lastMutateOptions().onError?.(new Error('')))

      expect(screen.getByRole('alert')).toHaveTextContent('Could not update Oat Milk')
    })
  })
})
