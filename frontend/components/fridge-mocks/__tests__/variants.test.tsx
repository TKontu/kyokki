/**
 * The fridge mocks (Q17-M). Each one must be able to replace FridgeView next round without
 * changing its test contract, so every variant is held to the same queries as
 * `components/inventory/__tests__/FridgeView.test.tsx`: the areas as regions in fridge order,
 * an "Open X" link each, the dots as one image, and no numbers anywhere.
 */

import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { STALENESS, stalenessOf } from '@/lib/staleness'
import type { InventoryItem } from '@/types/inventory'
import { FRIDGE_MOCKS } from '..'
import { fixtureItems } from '../fixtures'

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
const SALMON = item({
  id: 'item-salmon',
  product_name: 'Salmon',
  category: 'fish',
  category_icon: '🐟',
  expiry_date: inDays(30),
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

const FRIDGE_ORDER = [
  'Meat & fish', 'Veggies', 'Fruits', 'Dairy', 'Bread', 'Ready meals', 'Drinks',
  'Pantry', 'Freezer',
]

function area(name: string) {
  return screen.getByRole('region', { name })
}

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(TODAY)
})
afterEach(() => jest.useRealTimers())

it('offers two or three variants, each with a name and a line about it', () => {
  expect(FRIDGE_MOCKS.length).toBeGreaterThanOrEqual(2)
  expect(FRIDGE_MOCKS.length).toBeLessThanOrEqual(3)
  expect(new Set(FRIDGE_MOCKS.map((mock) => mock.id)).size).toBe(FRIDGE_MOCKS.length)
  for (const mock of FRIDGE_MOCKS) {
    expect(mock.name).toBeTruthy()
    expect(mock.description).toBeTruthy()
    expect(`${mock.name} ${mock.description}`).not.toMatch(/\d/)
  }
})

describe.each(FRIDGE_MOCKS.map((mock) => [mock.name, mock] as const))('%s', (_name, mock) => {
  const Fridge = mock.Component

  it('shows no numbers anywhere, drawing included', () => {
    const { container } = render(
      <Fridge items={fixtureItems()} onConsume={jest.fn()} onMore={jest.fn()} onClearExpired={jest.fn()} />
    )

    expect(container.textContent).not.toMatch(/\d/)
  })

  it('draws every area, in fridge order', () => {
    render(<Fridge items={[item()]} />)

    const names = screen.getAllByRole('region').map((region) => region.getAttribute('aria-label'))
    expect(names).toEqual(FRIDGE_ORDER)
  })

  it('adds Other last, only when something has no area', () => {
    render(<Fridge items={[item({ category: 'household', product_name: 'Soap' })]} />)

    const names = screen.getAllByRole('region').map((region) => region.getAttribute('aria-label'))
    expect(names).toEqual([...FRIDGE_ORDER, 'Other'])
    expect(within(area('Other')).getByRole('img')).toHaveAccessibleName('Soap keeps')
  })

  it('shows an area\'s items as a dot each, in their colour', () => {
    render(<Fridge items={[MINCE, OLD_HAM, SALMON, item()]} />)

    const dots = within(area('Meat & fish')).getByRole('img')
    expect(dots).toHaveAccessibleName('Ham going stale, Minced Meat going stale, Salmon keeps')
    expect(dots.children).toHaveLength(3)
    const expected = [OLD_HAM, MINCE, SALMON].map((each) => STALENESS[stalenessOf(each)].dot)
    Array.from(dots.children).forEach((dot, index) => {
      for (const cls of expected[index].split(' ')) expect(dot.classList).toContain(cls)
    })
    expect(dots.children[0].className).toMatch(/red/)
  })

  it('shows a few emoji of what is inside', () => {
    render(<Fridge items={[MINCE, SALMON]} />)

    expect(within(area('Meat & fish')).getByText('🐟')).toBeInTheDocument()
    expect(within(area('Meat & fish')).getByText('🥩')).toBeInTheDocument()
  })

  it('makes each whole area the link to its grid', () => {
    render(<Fridge items={[item()]} />)

    expect(within(area('Dairy')).getByRole('link', { name: 'Open Dairy' })).toHaveAttribute(
      'href',
      '/area/dairy'
    )
    expect(within(area('Freezer')).getByRole('link', { name: 'Open Freezer' })).toHaveAttribute(
      'href',
      '/area/freezer'
    )
  })

  it('files frozen things in the freezer', () => {
    render(<Fridge items={[PEAS]} />)

    expect(within(area('Freezer')).getByRole('img')).toHaveAccessibleName('Peas keeps')
    expect(within(area('Veggies')).queryByRole('img')).not.toBeInTheDocument()
  })

  it('hides its drawing from screen readers', () => {
    const { container } = render(<Fridge items={fixtureItems()} />)

    const svgs = Array.from(container.querySelectorAll('svg'))
    expect(svgs.length).toBeGreaterThan(0)
    for (const svg of svgs) expect(svg.closest('[aria-hidden="true"]')).not.toBeNull()
  })

  it('puts what is going stale on its shelf as tiles', () => {
    const onConsume = jest.fn()
    const onMore = jest.fn()
    render(<Fridge items={[item(), MINCE]} onConsume={onConsume} onMore={onMore} />)

    const shelf = area('Going stale')
    expect(within(shelf).queryByText('Oat Milk')).not.toBeInTheDocument()
    fireEvent.click(within(shelf).getByRole('button', { name: 'Minced Meat, going stale' }))
    expect(onConsume).toHaveBeenCalledWith('item-mince')
    fireEvent.click(within(shelf).getByRole('button', { name: 'More for Minced Meat' }))
    expect(onMore).toHaveBeenCalledWith('item-mince')
  })

  it('has no shelf when nothing is going stale', () => {
    render(<Fridge items={[item()]} />)

    expect(screen.queryByRole('region', { name: 'Going stale' })).not.toBeInTheDocument()
  })

  it('offers to clear what is past its date', () => {
    const onClearExpired = jest.fn()
    render(<Fridge items={[OLD_HAM, MINCE]} onClearExpired={onClearExpired} />)

    fireEvent.click(screen.getByRole('button', { name: 'Clear expired' }))

    expect(onClearExpired).toHaveBeenCalledWith([OLD_HAM])
  })

  it('offers no clear when nothing is past its date', () => {
    render(<Fridge items={[MINCE]} onClearExpired={jest.fn()} />)

    expect(screen.queryByRole('button', { name: 'Clear expired' })).not.toBeInTheDocument()
  })

  it('leaves out what is used up or thrown away', () => {
    render(<Fridge items={[item({ status: 'empty' }), item({ id: 'x', status: 'discarded' })]} />)

    expect(within(area('Dairy')).queryByRole('img')).not.toBeInTheDocument()
  })
})
