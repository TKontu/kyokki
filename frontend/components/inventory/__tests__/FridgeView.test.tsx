/**
 * The fridge main view (V3): a going-stale shelf across the top, then an area per kind of food,
 * each showing its items as coloured dots. No numbers anywhere on screen.
 */

import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { FridgeView } from '../FridgeView'
import type { InventoryItem } from '@/types/inventory'

jest.mock('@/hooks/useInventory')
import { useInventoryList } from '@/hooks/useInventory'
const mockUseInventoryList = useInventoryList as jest.Mock

const TODAY = new Date('2026-09-25T12:00:00')

function inDays(days: number): string {
  const date = new Date(TODAY)
  date.setDate(date.getDate() + days)
  return date.toISOString().split('T')[0]
}

const item = (overrides: Partial<InventoryItem> = {}): InventoryItem => ({
  id: 'item-milk',
  product_master_id: 'p1',
  product_name: 'Oat Milk',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: '🥛',
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 750,
  unit: 'dl',
  status: 'opened',
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

const MINCE = item({
  id: 'item-mince',
  product_name: 'Minced Meat',
  category: 'meat',
  category_icon: '🥩',
  expiry_date: inDays(1),
})
const PEAS = item({
  id: 'item-peas',
  product_name: 'Peas',
  category: 'produce',
  category_icon: '🫛',
  location: 'freezer',
  expiry_date: inDays(200),
})
const OLD_HAM = item({
  id: 'item-ham',
  product_name: 'Ham',
  category: 'meat',
  category_icon: '🥩',
  expiry_date: inDays(-2),
})

function mockItems(data: InventoryItem[] | undefined, rest: object = {}) {
  mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data, ...rest })
}

function area(name: string) {
  return screen.getByRole('region', { name })
}

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(TODAY)
  mockUseInventoryList.mockReset()
})
afterEach(() => jest.useRealTimers())

describe('FridgeView', () => {
  it('shows no numbers anywhere', () => {
    mockItems([item(), MINCE, PEAS, OLD_HAM])
    const { container } = render(<FridgeView />)

    expect(container.textContent).not.toMatch(/\d/)
  })

  it('puts what is going stale on the shelf across the top', () => {
    mockItems([item(), MINCE])
    render(<FridgeView onConsume={jest.fn()} />)

    const shelf = area('Going stale')
    expect(within(shelf).getByRole('button', { name: 'Minced Meat, going stale' })).toBeInTheDocument()
    expect(within(shelf).queryByText('Oat Milk')).not.toBeInTheDocument()
  })

  it('has no shelf when nothing is going stale', () => {
    mockItems([item()])
    render(<FridgeView />)

    expect(screen.queryByRole('region', { name: 'Going stale' })).not.toBeInTheDocument()
  })

  it('draws every area, in fridge order', () => {
    mockItems([item()])
    render(<FridgeView />)

    const names = screen
      .getAllByRole('region')
      .map((region) => region.getAttribute('aria-label'))
    expect(names).toEqual([
      'Meat & fish', 'Veggies', 'Fruits', 'Dairy', 'Bread', 'Ready meals', 'Drinks',
      'Pantry', 'Freezer',
    ])
  })

  it('shows an area\'s items as a dot each, in their colour', () => {
    mockItems([MINCE, OLD_HAM, item()])
    render(<FridgeView />)

    const dots = within(area('Meat & fish')).getByRole('img')
    expect(dots).toHaveAccessibleName('Ham going stale, Minced Meat going stale')
    expect(dots.children).toHaveLength(2)
    expect(dots.children[0].className).toMatch(/red/)
  })

  it('opens an area\'s grid', () => {
    mockItems([item()])
    render(<FridgeView />)

    expect(within(area('Dairy')).getByRole('link', { name: 'Open Dairy' })).toHaveAttribute(
      'href',
      '/area/dairy'
    )
  })

  it('files frozen things in the freezer', () => {
    mockItems([PEAS])
    render(<FridgeView />)

    expect(within(area('Freezer')).getByRole('img')).toHaveAccessibleName('Peas keeps')
    expect(within(area('Veggies')).queryByRole('img')).not.toBeInTheDocument()
  })

  it('shows Other only when something has no area', () => {
    mockItems([item({ category: 'household', product_name: 'Soap' })])
    render(<FridgeView />)

    expect(within(area('Other')).getByRole('img')).toHaveAccessibleName('Soap keeps')
  })

  it('uses a shelf item up with one tap', () => {
    const onConsume = jest.fn()
    mockItems([MINCE])
    render(<FridgeView onConsume={onConsume} />)

    fireEvent.click(screen.getByRole('button', { name: 'Minced Meat, going stale' }))

    expect(onConsume).toHaveBeenCalledWith('item-mince')
  })

  it('opens more for a shelf item', () => {
    const onMore = jest.fn()
    mockItems([MINCE])
    render(<FridgeView onConsume={jest.fn()} onMore={onMore} />)

    fireEvent.click(screen.getByRole('button', { name: 'More for Minced Meat' }))

    expect(onMore).toHaveBeenCalledWith('item-mince')
  })

  it('offers to clear what is past its date', () => {
    const onClearExpired = jest.fn()
    mockItems([OLD_HAM, MINCE])
    render(<FridgeView onClearExpired={onClearExpired} />)

    fireEvent.click(screen.getByRole('button', { name: 'Clear expired' }))

    expect(onClearExpired).toHaveBeenCalledWith([OLD_HAM])
  })

  it('offers no clear when nothing is past its date', () => {
    mockItems([MINCE])
    render(<FridgeView onClearExpired={jest.fn()} />)

    expect(screen.queryByRole('button', { name: 'Clear expired' })).not.toBeInTheDocument()
  })

  it('leaves out what is used up or thrown away', () => {
    mockItems([item({ status: 'empty' }), item({ id: 'x', status: 'discarded' })])
    render(<FridgeView />)

    expect(screen.getByText(/No items found/)).toBeInTheDocument()
  })

  it('names the ways stock actually gets in when the fridge is empty', () => {
    mockItems([])
    render(<FridgeView />)

    expect(screen.getByText(/\+ Add/)).toBeInTheDocument()
    expect(screen.getByText(/Telegram bot/)).toBeInTheDocument()
  })

  it('shows placeholders while loading', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    render(<FridgeView />)

    expect(screen.getByLabelText('Loading inventory')).toBeInTheDocument()
  })

  it('says so when the first load fails', () => {
    mockItems(undefined, { isError: true, error: new Error('Network down') })
    render(<FridgeView />)

    expect(screen.getByRole('alert')).toHaveTextContent('Network down')
  })

  it('keeps the stock it already has when a refresh fails', () => {
    mockItems([MINCE], { isError: true, error: new Error('Network down') })
    render(<FridgeView onConsume={jest.fn()} />)

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Minced Meat, going stale' })).toBeInTheDocument()
  })
})
