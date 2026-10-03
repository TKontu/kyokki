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
  window.localStorage.clear()
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

  it('gives the "…" button a 44px touch target, not its 32px glyph box', () => {
    render(<IngredientTile item={MILK} onSelect={jest.fn()} onMore={jest.fn()} />)

    const more = screen.getByRole('button', { name: 'More for Oat Milk' })
    expect(more.className).toMatch(/\bh-touch\b/)
    expect(more.className).toMatch(/\bw-touch\b/)
    expect(more.className).not.toMatch(/\bh-8\b/)
  })

  it('keeps the "…" button corner-flush so the bigger target does not overlap the tile (F7)', () => {
    render(<IngredientTile item={MILK} onSelect={jest.fn()} onMore={jest.fn()} />)

    const more = screen.getByRole('button', { name: 'More for Oat Milk' })
    expect(more.className).toMatch(/\bright-0\b/)
    expect(more.className).toMatch(/\btop-0\b/)
    expect(more.className).not.toMatch(/\bright-1\b/)
    expect(more.className).not.toMatch(/\btop-1\b/)
  })

  it('falls back to a plain box without a category emoji', () => {
    const { container } = render(<IngredientTile item={{ ...MILK, category_icon: null }} />)

    expect(container).toHaveTextContent('Oat Milk')
  })

  describe('the generated icon (Q18-G2)', () => {
    it('shows the product its own generated image instead of the category emoji', () => {
      const { container } = render(
        <IngredientTile item={{ ...MILK, product_icon_version: 1790000000 }} />
      )

      const img = container.querySelector('img')
      expect(img).not.toBeNull()
      expect(img?.getAttribute('src')).toMatch(/\/products\/p1\/icon\.png\?v=1790000000$/)
      expect(img).toHaveAttribute('alt', '')
      expect(img).toHaveAttribute('aria-hidden', 'true')
      expect(container).not.toHaveTextContent('🥛')
    })

    it('keeps the emoji when there is no generated image', () => {
      const { container } = render(
        <IngredientTile item={{ ...MILK, product_icon_version: null }} />
      )

      expect(container.querySelector('img')).toBeNull()
      expect(container).toHaveTextContent('🥛')
    })

    it('falls back to the emoji when the generated image does not load', () => {
      const { container } = render(
        <IngredientTile item={{ ...MILK, product_icon_version: 1790000000 }} />
      )

      fireEvent.error(container.querySelector('img') as HTMLImageElement)

      expect(container.querySelector('img')).toBeNull()
      expect(container).toHaveTextContent('🥛')
    })

    it('tries again when a new version arrives', () => {
      const { container, rerender } = render(
        <IngredientTile item={{ ...MILK, product_icon_version: 1 }} />
      )
      fireEvent.error(container.querySelector('img') as HTMLImageElement)

      rerender(<IngredientTile item={{ ...MILK, product_icon_version: 2 }} />)

      expect(container.querySelector('img')?.getAttribute('src')).toMatch(/\?v=2$/)
    })

    it('keeps its accessible name and no numbers in its text', () => {
      const { container } = render(
        <IngredientTile
          item={{ ...MILK, product_icon_version: 1790000000 }}
          onSelect={jest.fn()}
        />
      )

      expect(screen.getByRole('button', { name: 'Oat Milk, going stale' })).toBeInTheDocument()
      expect(container.textContent).not.toMatch(/\d/)
    })
  })

  describe('the exact emoji (Q18 build)', () => {
    it('shows product_emoji ahead of the generated image', () => {
      const { container } = render(
        <IngredientTile
          item={{ ...MILK, product_emoji: '🥛', product_icon_version: 1790000000 }}
        />
      )

      expect(container.querySelector('img')).toBeNull()
      expect(container).toHaveTextContent('🥛')
    })

    it('shows product_emoji ahead of the category emoji', () => {
      const { container } = render(
        <IngredientTile item={{ ...MILK, product_emoji: '🍼', category_icon: '🥛' }} />
      )

      expect(container).toHaveTextContent('🍼')
      expect(container).not.toHaveTextContent('🥛')
    })

    it('falls back to the generated image when there is no product_emoji', () => {
      const { container } = render(
        <IngredientTile
          item={{ ...MILK, product_emoji: null, product_icon_version: 1790000000 }}
        />
      )

      expect(container.querySelector('img')).not.toBeNull()
    })

    it('falls back to the category emoji when a broken generated image has no product_emoji', () => {
      const { container } = render(
        <IngredientTile
          item={{ ...MILK, product_emoji: null, product_icon_version: 1790000000 }}
        />
      )

      fireEvent.error(container.querySelector('img') as HTMLImageElement)

      expect(container.querySelector('img')).toBeNull()
      expect(container).toHaveTextContent('🥛')
    })
  })

  describe('display language (Post-MVP frontier item 13)', () => {
    const WITH_FI = { ...MILK, product_display_names: { fi: 'Kauramaito' } }

    it('shows the English name by default', () => {
      const { container } = render(<IngredientTile item={WITH_FI} />)

      expect(container).toHaveTextContent('Oat Milk')
      expect(container).not.toHaveTextContent('Kauramaito')
    })

    it('shows the Finnish name once the cook has chosen Suomi', () => {
      window.localStorage.setItem('kyokki.language', 'fi')

      const { container } = render(<IngredientTile item={WITH_FI} />)

      expect(container).toHaveTextContent('Kauramaito')
      expect(container).not.toHaveTextContent('Oat Milk')
    })

    it('falls back to the English name in Suomi when there is no Finnish one', () => {
      window.localStorage.setItem('kyokki.language', 'fi')

      const { container } = render(<IngredientTile item={MILK} />)

      expect(container).toHaveTextContent('Oat Milk')
    })
  })
})
