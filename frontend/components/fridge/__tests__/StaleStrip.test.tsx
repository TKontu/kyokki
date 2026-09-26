/**
 * The going-stale strip across the top of the portrait fridge (Q17-B): it never scrolls
 * sideways. What does not fit waits behind a "more" tile that opens every going-stale item.
 */

import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { STALE_STRIP_MAX, StaleStrip } from '../StaleStrip'
import { TODAY, item, inDays, stale } from '../__fixtures__/stock'

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(TODAY)
})
afterEach(() => jest.useRealTimers())

function shelf() {
  return screen.getByRole('region', { name: 'Going stale' })
}

function tiles() {
  return within(shelf()).getAllByRole('button', { name: /, going stale$/ })
}

describe('StaleStrip', () => {
  it('shows every tile when they fit, and no more tile', () => {
    render(<StaleStrip items={stale(STALE_STRIP_MAX)} expired={[]} onConsume={jest.fn()} />)

    expect(tiles()).toHaveLength(STALE_STRIP_MAX)
    expect(screen.queryByRole('button', { name: 'All going stale' })).not.toBeInTheDocument()
  })

  it('shows what fits and a more tile, never a sideways scroll', () => {
    const { container } = render(
      <StaleStrip items={stale(12)} expired={[]} onConsume={jest.fn()} onMore={jest.fn()} />
    )

    expect(tiles()).toHaveLength(STALE_STRIP_MAX - 1)
    expect(within(shelf()).getByRole('button', { name: 'All going stale' })).toBeInTheDocument()
    expect(container.innerHTML).not.toMatch(/overflow-x-auto|overflow-auto/)
    expect(container.textContent).not.toMatch(/\d/)
  })

  it('opens every going-stale item from the more tile', () => {
    const onConsume = jest.fn()
    render(<StaleStrip items={stale(12)} expired={[]} onConsume={onConsume} onMore={jest.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'All going stale' }))

    const sheet = screen.getByRole('dialog', { name: 'Going stale' })
    expect(within(sheet).getAllByRole('button', { name: /, going stale$/ })).toHaveLength(12)
    expect(sheet.textContent).not.toMatch(/\d/)
    fireEvent.click(within(sheet).getByRole('button', { name: 'Stale Lima, going stale' }))
    expect(onConsume).toHaveBeenCalledWith('stale-11')
  })

  it("closes the list before opening an item's sheet from it", () => {
    const onMore = jest.fn()
    render(<StaleStrip items={stale(12)} expired={[]} onConsume={jest.fn()} onMore={onMore} />)

    fireEvent.click(screen.getByRole('button', { name: 'All going stale' }))
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'More for Stale Lima' })
    )

    expect(onMore).toHaveBeenCalledWith('stale-11')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('offers to clear what is past its date', () => {
    const onClearExpired = jest.fn()
    const old = item({ id: 'old', product_name: 'Ham', category: 'meat', expiry_date: inDays(-2) })
    render(<StaleStrip items={[old]} expired={[old]} onClearExpired={onClearExpired} />)

    fireEvent.click(screen.getByRole('button', { name: 'Clear expired' }))

    expect(onClearExpired).toHaveBeenCalledWith([old])
  })

  it('is not there when nothing is going stale', () => {
    render(<StaleStrip items={[]} expired={[]} />)

    expect(screen.queryByRole('region', { name: 'Going stale' })).not.toBeInTheDocument()
  })
})
