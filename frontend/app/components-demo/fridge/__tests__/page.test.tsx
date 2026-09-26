/**
 * The fridge mocks' demo page (Q17-M): pick a design, see it on live stock, or on sample stock
 * when the homelab has none.
 */

import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { InventoryItem } from '@/types/inventory'
import { FRIDGE_MOCKS } from '@/components/fridge-mocks'
import FridgeMocksPage from '../page'

jest.mock('@/hooks/useInventory')
import { useInventoryList } from '@/hooks/useInventory'
const mockUseInventoryList = useInventoryList as jest.Mock

const PEAS: InventoryItem = {
  id: 'item-peas',
  product_master_id: 'p1',
  product_name: 'Peas',
  category: 'produce',
  category_name: 'Produce',
  category_icon: '🫛',
  receipt_id: null,
  initial_quantity: 1,
  current_quantity: 1,
  unit: 'pcs',
  status: 'sealed',
  purchase_date: '2026-09-20',
  expiry_date: '2027-06-01',
  expiry_source: 'calculated',
  opened_date: null,
  batch_number: null,
  location: 'freezer',
  notes: null,
  created_at: '2026-09-20T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
}

function mockItems(data: InventoryItem[] | undefined, rest: object = {}) {
  mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data, ...rest })
}

function designButton(name: string) {
  return within(screen.getByRole('group', { name: 'Design' })).getByRole('button', {
    name: new RegExp(`^${name}`),
  })
}

beforeEach(() => {
  mockUseInventoryList.mockReset()
  window.history.replaceState(null, '', '/components-demo/fridge')
  document.documentElement.classList.remove('dark', 'light')
})

describe('fridge mocks page', () => {
  it('offers every design, with its name and what it is', () => {
    mockItems([PEAS])
    render(<FridgeMocksPage />)

    for (const mock of FRIDGE_MOCKS) {
      expect(designButton(mock.name)).toHaveTextContent(mock.description)
    }
  })

  it('shows the first design on live stock to begin with', () => {
    mockItems([PEAS])
    render(<FridgeMocksPage />)

    expect(designButton(FRIDGE_MOCKS[0].name)).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId(`fridge-mock-${FRIDGE_MOCKS[0].id}`)).toBeInTheDocument()
    expect(
      within(screen.getByRole('region', { name: 'Freezer' })).getByRole('img')
    ).toHaveAccessibleName('Peas keeps')
  })

  it('switches design', () => {
    mockItems([PEAS])
    render(<FridgeMocksPage />)

    const second = FRIDGE_MOCKS[1]
    fireEvent.click(designButton(second.name))

    expect(designButton(second.name)).toHaveAttribute('aria-pressed', 'true')
    expect(designButton(FRIDGE_MOCKS[0].name)).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId(`fridge-mock-${second.id}`)).toBeInTheDocument()
    expect(screen.queryByTestId(`fridge-mock-${FRIDGE_MOCKS[0].id}`)).not.toBeInTheDocument()
  })

  it('fills an empty homelab with sample stock on request', () => {
    mockItems([])
    render(<FridgeMocksPage />)

    expect(within(screen.getByRole('region', { name: 'Dairy' })).queryByRole('img')).toBeNull()

    const sample = screen.getByRole('button', { name: 'Sample stock' })
    fireEvent.click(sample)

    expect(sample).toHaveAttribute('aria-pressed', 'true')
    expect(within(screen.getByRole('region', { name: 'Dairy' })).getByRole('img')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Other' })).toBeInTheDocument()
  })

  it('opens on the design and stock the address names', () => {
    mockItems([])
    const last = FRIDGE_MOCKS[FRIDGE_MOCKS.length - 1]
    window.history.replaceState(null, '', `/components-demo/fridge?design=${last.id}&sample=on`)
    render(<FridgeMocksPage />)

    expect(designButton(last.name)).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Sample stock' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('switches to dark and back', () => {
    mockItems([])
    render(<FridgeMocksPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Dark' }))
    expect(document.documentElement).toHaveClass('dark')

    fireEvent.click(screen.getByRole('button', { name: 'Light' }))
    expect(document.documentElement).toHaveClass('light')
    expect(document.documentElement).not.toHaveClass('dark')
  })

  it('says so while live stock loads', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    render(<FridgeMocksPage />)

    expect(screen.getByLabelText('Loading inventory')).toBeInTheDocument()
  })

  it('says so when live stock fails to load', () => {
    mockItems(undefined, { isError: true, error: new Error('Network down') })
    render(<FridgeMocksPage />)

    expect(screen.getByRole('alert')).toHaveTextContent('Network down')
  })
})
