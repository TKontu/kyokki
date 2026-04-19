import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { InventoryItemCard } from '../InventoryItemCard'
import type { InventoryItem } from '@/types/inventory'

const MOCK_NOW = new Date('2024-02-01T12:00:00Z')

const MOCK_ITEM: InventoryItem = {
  id: 'abc123',
  product_master_id: 'def456',
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 750,
  unit: 'ml',
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

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(MOCK_NOW)
})

afterEach(() => {
  jest.useRealTimers()
})

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('TestInventoryItemCardRendering', () => {
  it('renders product name', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    expect(screen.getByText('Oat Milk')).toBeInTheDocument()
  })

  it('renders category when provided', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        productCategory="Dairy Alternatives"
      />
    )
    expect(screen.getByText(/Dairy Alternatives/)).toBeInTheDocument()
  })

  it('omits category separator when not provided', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    expect(screen.queryByText(/·/)).not.toBeInTheDocument()
  })

  it('renders location label for main_fridge', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    expect(screen.getByText(/Main Fridge/)).toBeInTheDocument()
  })

  it('renders location label for freezer', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, location: 'freezer' }}
        productName="Ice Cream"
      />
    )
    expect(screen.getByText(/Freezer/)).toBeInTheDocument()
  })

  it('renders location label for pantry', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, location: 'pantry' }}
        productName="Pasta"
      />
    )
    expect(screen.getByText(/Pantry/)).toBeInTheDocument()
  })

  it('renders ExpiryBadge', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    // ExpiryBadge renders a span with expiry text — 28 days away from MOCK_NOW
    expect(screen.getByText(/week|days?|month/i)).toBeInTheDocument()
  })

  it('renders QuantityBar with current/initial', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    expect(screen.getByText(/750/)).toBeInTheDocument()
    expect(screen.getByText(/1000/)).toBeInTheDocument()
  })

  it('renders status badge', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    expect(screen.getByText('Opened')).toBeInTheDocument()
  })

  it('renders category · location when both provided', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        productCategory="Dairy Alternatives"
      />
    )
    expect(screen.getByText(/Dairy Alternatives · Main Fridge/)).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

describe('TestInventoryItemCardStatus', () => {
  it('sealed shows success badge', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'sealed' }}
        productName="Milk"
      />
    )
    expect(screen.getByText('Sealed')).toBeInTheDocument()
  })

  it('opened shows info badge', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Milk" />)
    expect(screen.getByText('Opened')).toBeInTheDocument()
  })

  it('partial shows warning badge', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'partial' }}
        productName="Milk"
      />
    )
    expect(screen.getByText('Partial')).toBeInTheDocument()
  })

  it('empty shows default badge', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'empty' }}
        productName="Milk"
      />
    )
    expect(screen.getByText('Empty')).toBeInTheDocument()
  })

  it('discarded shows error badge', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'discarded' }}
        productName="Milk"
      />
    )
    expect(screen.getByText('Discarded')).toBeInTheDocument()
  })

  it('empty item has reduced opacity', () => {
    const { container } = render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'empty' }}
        productName="Milk"
      />
    )
    expect((container.firstChild as HTMLElement).className).toContain('opacity-60')
  })

  it('discarded item has reduced opacity', () => {
    const { container } = render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'discarded' }}
        productName="Milk"
      />
    )
    expect((container.firstChild as HTMLElement).className).toContain('opacity-60')
  })

  it('active item does not have reduced opacity', () => {
    const { container } = render(
      <InventoryItemCard item={MOCK_ITEM} productName="Milk" />
    )
    expect((container.firstChild as HTMLElement).className).not.toContain('opacity-60')
  })
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

describe('TestInventoryItemCardActions', () => {
  it('consume button calls onConsume with item id', () => {
    const onConsume = jest.fn()
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onConsume={onConsume}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /consume/i }))
    expect(onConsume).toHaveBeenCalledWith('abc123')
  })

  it('edit button calls onEdit with item id', () => {
    const onEdit = jest.fn()
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onEdit={onEdit}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /edit/i }))
    expect(onEdit).toHaveBeenCalledWith('abc123')
  })

  it('renders no footer when no handlers provided', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders only consume button when only onConsume provided', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onConsume={jest.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /consume/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
  })

  it('renders only edit button when only onEdit provided', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onEdit={jest.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /consume/i })).not.toBeInTheDocument()
  })

  it('consume button is disabled for empty items', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'empty' }}
        productName="Oat Milk"
        onConsume={jest.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /consume/i })).toBeDisabled()
  })

  it('consume button is disabled for discarded items', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'discarded' }}
        productName="Oat Milk"
        onConsume={jest.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /consume/i })).toBeDisabled()
  })

  it('consume button is enabled for active items', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onConsume={jest.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /consume/i })).not.toBeDisabled()
  })

  it('edit button is not disabled for empty items', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'empty' }}
        productName="Oat Milk"
        onEdit={jest.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /edit/i })).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Touch Targets
// ---------------------------------------------------------------------------

describe('TestInventoryItemCardTouchTargets', () => {
  it('consume button has min-h-touch class (44px touch target)', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onConsume={jest.fn()}
      />
    )
    const btn = screen.getByRole('button', { name: /consume/i })
    expect(btn.className).toContain('min-h-touch')
  })

  it('edit button has min-h-touch class (44px touch target)', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onEdit={jest.fn()}
      />
    )
    const btn = screen.getByRole('button', { name: /edit/i })
    expect(btn.className).toContain('min-h-touch')
  })
})

// ---------------------------------------------------------------------------
// Custom className
// ---------------------------------------------------------------------------

describe('TestInventoryItemCardClassName', () => {
  it('applies custom className to card root', () => {
    const { container } = render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        className="my-custom-class"
      />
    )
    expect((container.firstChild as HTMLElement).className).toContain(
      'my-custom-class'
    )
  })
})
