import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { ShoppingItemRow } from '../ShoppingItemRow'
import { LANGUAGE_KEY } from '@/lib/language'
import type { ShoppingListItem } from '@/types/shopping'

const ITEM: ShoppingListItem = {
  id: 'i-1',
  product_master_id: null,
  name: 'Bananas',
  quantity: 6,
  unit: 'pcs',
  priority: 'urgent',
  source: 'manual',
  is_purchased: false,
  added_at: '2026-10-01T10:00:00Z',
  purchased_at: null,
}

describe('ShoppingItemRow', () => {
  it('shows the name and amount', () => {
    render(<ShoppingItemRow item={ITEM} onToggle={jest.fn()} onRemove={jest.fn()} />)

    expect(screen.getByText('Bananas')).toBeInTheDocument()
    expect(screen.getByText('6 pcs')).toBeInTheDocument()
  })

  it('marks an auto-added item with an icon and the word "Auto"', () => {
    render(
      <ShoppingItemRow
        item={{ ...ITEM, source: 'auto_restock' }}
        onToggle={jest.fn()}
        onRemove={jest.fn()}
      />
    )

    expect(screen.getByText('Auto')).toBeInTheDocument()
  })

  it('does not mark a manually added item', () => {
    render(<ShoppingItemRow item={ITEM} onToggle={jest.fn()} onRemove={jest.fn()} />)

    expect(screen.queryByText('Auto')).not.toBeInTheDocument()
  })

  it('badges an open urgent item, and nothing once it is bought', () => {
    const { rerender } = render(
      <ShoppingItemRow item={ITEM} onToggle={jest.fn()} onRemove={jest.fn()} />
    )
    expect(screen.getByText('Urgent')).toBeInTheDocument()

    rerender(
      <ShoppingItemRow
        item={{ ...ITEM, is_purchased: true }}
        onToggle={jest.fn()}
        onRemove={jest.fn()}
      />
    )
    expect(screen.queryByText('Urgent')).not.toBeInTheDocument()
  })

  it('toggles on tap', () => {
    const onToggle = jest.fn()
    render(<ShoppingItemRow item={ITEM} onToggle={onToggle} onRemove={jest.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Mark Bananas bought' }))

    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('offers to mark a bought item not bought', () => {
    render(
      <ShoppingItemRow item={{ ...ITEM, is_purchased: true }} onToggle={jest.fn()} onRemove={jest.fn()} />
    )

    expect(screen.getByRole('button', { name: 'Mark Bananas not bought' })).toBeInTheDocument()
  })

  it('removes on the "…" button', () => {
    const onRemove = jest.fn()
    render(<ShoppingItemRow item={ITEM} onToggle={jest.fn()} onRemove={onRemove} />)

    fireEvent.click(screen.getByRole('button', { name: 'Remove Bananas' }))

    expect(onRemove).toHaveBeenCalledTimes(1)
  })

  describe('display names (Post-MVP frontier item 13, phase 2)', () => {
    afterEach(() => window.localStorage.clear())

    it('shows the linked product\'s Finnish name once Suomi is chosen', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      render(
        <ShoppingItemRow
          item={{ ...ITEM, name: 'Milk', product_master_id: 'p-1', product_display_names: { fi: 'Maito' } }}
          onToggle={jest.fn()}
          onRemove={jest.fn()}
        />
      )

      expect(screen.getByText('Maito')).toBeInTheDocument()
      expect(screen.queryByText('Milk')).not.toBeInTheDocument()
    })

    it('keeps the cook\'s own wording for a free-text item, even in Finnish', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      render(<ShoppingItemRow item={ITEM} onToggle={jest.fn()} onRemove={jest.fn()} />)

      expect(screen.getByText('Bananas')).toBeInTheDocument()
    })

    it('reads the row\'s own chrome - Auto, Urgent, the toggle label - in Finnish', () => {
      window.localStorage.setItem(LANGUAGE_KEY, 'fi')
      render(
        <ShoppingItemRow
          item={{ ...ITEM, source: 'auto_restock' }}
          onToggle={jest.fn()}
          onRemove={jest.fn()}
        />
      )

      expect(screen.getByText('Autom.')).toBeInTheDocument()
      expect(screen.getByText('Kiireellinen')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Merkitse Bananas ostetuksi' })).toBeInTheDocument()
    })
  })
})
