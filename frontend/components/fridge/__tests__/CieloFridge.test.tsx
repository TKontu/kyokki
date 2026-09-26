/**
 * The production fridge on `/` (Q17-B): Cielo redrawn for the portrait iPad. It keeps
 * FridgeView's contract (held there) and adds what the mocks lacked: a region that holds more
 * dots than it has room for says so with a visible marker, and no two areas overlap.
 */

import React from 'react'
import { render, screen, within } from '@testing-library/react'
import { AREAS } from '@/lib/fridge'
import { fixtureItems } from '@/components/fridge-mocks/fixtures'
import { CIELO_BOX, CIELO_HEIGHT, CIELO_WIDTH, CieloFridge } from '../CieloFridge'
import { dotCapacity } from '../capacity'
import { crowdedItems } from '../__fixtures__/crowded'
import { TODAY, item, many } from '../__fixtures__/stock'

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(TODAY)
})
afterEach(() => jest.useRealTimers())

function area(name: string) {
  return screen.getByRole('region', { name })
}

describe('CieloFridge', () => {
  it('is drawn for a portrait screen', () => {
    expect(CIELO_HEIGHT).toBeGreaterThanOrEqual(CIELO_WIDTH * 0.9)
  })

  it('lays every area inside the drawing, none over another', () => {
    const boxes = AREAS.map((each) => [each.id, CIELO_BOX[each.id]] as const)
    for (const [, box] of boxes) {
      expect(box.x).toBeGreaterThanOrEqual(0)
      expect(box.y).toBeGreaterThanOrEqual(0)
      expect(box.x + box.w).toBeLessThanOrEqual(CIELO_WIDTH)
      expect(box.y + box.h).toBeLessThanOrEqual(CIELO_HEIGHT)
    }
    for (const [a, one] of boxes) {
      for (const [b, other] of boxes) {
        if (a === b) continue
        const apart =
          one.x + one.w <= other.x ||
          other.x + other.w <= one.x ||
          one.y + one.h <= other.y ||
          other.y + other.h <= one.y
        expect(`${a}/${b}: ${apart}`).toBe(`${a}/${b}: true`)
      }
    }
  })

  it('gives every area room for a row of dots at least', () => {
    for (const each of AREAS) expect(dotCapacity(CIELO_BOX[each.id])).toBeGreaterThanOrEqual(6)
  })

  it('shows every dot, and no marker, when they fit', () => {
    render(<CieloFridge items={[item()]} />)

    const dots = within(area('Dairy')).getByRole('img')
    expect(dots.children).toHaveLength(1)
    expect(within(area('Dairy')).queryByTestId('more-dots')).not.toBeInTheDocument()
  })

  it('marks a region that holds more than it can show, instead of cutting it off', () => {
    const capacity = dotCapacity(CIELO_BOX.meat)
    const meat = many(capacity + 3, { category: 'meat', category_icon: '🥩' })
    render(<CieloFridge items={meat} />)

    const dots = within(area('Meat & fish')).getByRole('img')
    // Every item is still named for a screen reader...
    expect(dots.getAttribute('aria-label')?.split(', ')).toHaveLength(capacity + 3)
    // ...and the last slot is the marker, not a dot
    expect(dots.children).toHaveLength(capacity)
    const marker = within(area('Meat & fish')).getByTestId('more-dots')
    expect(dots.lastElementChild).toBe(marker)
    expect(marker.textContent).not.toMatch(/\d/)
    expect(marker.textContent?.trim()).not.toBe('')
  })

  it('shows no numbers anywhere on a crowded fridge', () => {
    const { container } = render(
      <CieloFridge
        items={crowdedItems()}
        onConsume={jest.fn()}
        onMore={jest.fn()}
        onClearExpired={jest.fn()}
      />
    )

    expect(container.textContent).not.toMatch(/\d/)
    for (const each of AREAS) {
      expect(within(area(each.label)).getByTestId('more-dots')).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'All going stale' })).toBeInTheDocument()
  })

  it('shows no numbers on the sample stock', () => {
    const { container } = render(<CieloFridge items={fixtureItems()} onConsume={jest.fn()} />)

    expect(container.textContent).not.toMatch(/\d/)
  })

  it('hides its drawing from screen readers', () => {
    const { container } = render(<CieloFridge items={fixtureItems()} />)

    const svgs = Array.from(container.querySelectorAll('svg'))
    expect(svgs.length).toBeGreaterThan(0)
    for (const svg of svgs) expect(svg.closest('[aria-hidden="true"]')).not.toBeNull()
  })

  it('draws Other only when something has no area', () => {
    render(<CieloFridge items={[item()]} />)

    expect(screen.queryByRole('region', { name: 'Other' })).not.toBeInTheDocument()
  })
})
