/**
 * An ingredient tile (V1): a rounded box with the category emoji and the name, coloured by how
 * soon to eat it. No numbers - the colour, and its word for screen readers, carry that.
 */

import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { IngredientTile } from '../IngredientTile'
import type { InventoryItem } from '@/types/inventory'

const TODAY = new Date('2026-09-25T12:00:00')

const MILK: InventoryItem = {
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
  expiry_date: '2026-09-26',
  expiry_source: 'calculated',
  opened_date: '2026-09-21',
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2026-09-20T10:00:00Z',
  consumed_at: null,
  opened_shelf_life_days: null,
  avg_piece_grams: null,
}

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(TODAY)
})
afterEach(() => jest.useRealTimers())

describe('IngredientTile', () => {
  it('shows the emoji and the name, and no numbers', () => {
    const { container } = render(<IngredientTile item={MILK} />)

    expect(container).toHaveTextContent('🥛')
    expect(container).toHaveTextContent('Oat Milk')
    expect(container.textContent).not.toMatch(/\d/)
  })

  it('says its staleness in words', () => {
    render(<IngredientTile item={MILK} onSelect={jest.fn()} />)

    expect(screen.getByRole('button', { name: 'Oat Milk, going stale' })).toBeInTheDocument()
  })

  it('wears its tier colour', () => {
    render(<IngredientTile item={{ ...MILK, expiry_date: '2026-10-30' }} onSelect={jest.fn()} />)

    expect(screen.getByRole('button', { name: 'Oat Milk, keeps' }).className).toMatch(/blue/)
  })

  it('strikes the name through once used up', () => {
    render(<IngredientTile item={{ ...MILK, status: 'empty' }} onSelect={jest.fn()} />)

    expect(screen.getByText('Oat Milk')).toHaveClass('line-through')
  })

  it('tells the page which item was tapped', () => {
    const onSelect = jest.fn()
    render(<IngredientTile item={MILK} onSelect={onSelect} />)

    fireEvent.click(screen.getByRole('button', { name: /Oat Milk/ }))

    expect(onSelect).toHaveBeenCalledWith('item-milk')
  })

  it('offers more behind its own button', () => {
    const onMore = jest.fn()
    render(<IngredientTile item={MILK} onSelect={jest.fn()} onMore={onMore} />)

    fireEvent.click(screen.getByRole('button', { name: 'More for Oat Milk' }))

    expect(onMore).toHaveBeenCalledWith('item-milk')
  })

  it('falls back to a plain box without a category emoji', () => {
    const { container } = render(<IngredientTile item={{ ...MILK, category_icon: null }} />)

    expect(container).toHaveTextContent('Oat Milk')
  })
})
