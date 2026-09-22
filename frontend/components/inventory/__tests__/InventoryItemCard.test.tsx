import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { InventoryItemCard } from '../InventoryItemCard'
import type { InventoryItem } from '@/types/inventory'

const MOCK_NOW = new Date('2024-02-01T12:00:00Z')

const MOCK_ITEM: InventoryItem = {
  id: 'abc123',
  product_master_id: 'def456',
  product_name: 'Oat Milk',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: '🥛',
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

  it('omits the location when showLocation is false', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        productCategory="Dairy Alternatives"
        showLocation={false}
      />
    )
    expect(screen.getByText('Dairy Alternatives')).toBeInTheDocument()
    expect(screen.queryByText(/Main Fridge/)).not.toBeInTheDocument()
  })

  it('shows an unknown location as its raw value', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, location: 'garage' as InventoryItem['location'] }}
        productName="Oat Milk"
      />
    )
    expect(screen.getByText('garage')).toBeInTheDocument()
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
  // One tap consumes, no sheet (operator, 2026-09-22): the big button is the usual step and is
  // meant to be pressed again; "Done"/"All" finishes it; "…" is for any other amount.

  it('one tap on the big button consumes a quarter of a measured pack', () => {
    const onConsume = jest.fn()
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" onConsume={onConsume} />)

    fireEvent.click(screen.getByRole('button', { name: 'Consume 250 dl of Oat Milk' }))

    expect(onConsume).toHaveBeenCalledWith('abc123', 250)
    expect(screen.getByRole('button', { name: 'Consume 250 dl of Oat Milk' })).toHaveTextContent(
      '−¼ · 250 dl'
    )
  })

  it('the big button can be pressed again and again', () => {
    const onConsume = jest.fn()
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" onConsume={onConsume} />)

    const step = screen.getByRole('button', { name: 'Consume 250 dl of Oat Milk' })
    fireEvent.click(step)
    fireEvent.click(step)

    expect(onConsume).toHaveBeenCalledTimes(2)
  })

  it('takes one piece of something counted, and "All" takes the rest', () => {
    const onConsume = jest.fn()
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, unit: 'pcs', initial_quantity: 6, current_quantity: 4 }}
        productName="Apples"
        onConsume={onConsume}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Consume 1 pcs of Apples' }))
    fireEvent.click(screen.getByRole('button', { name: 'Finish Apples' }))

    expect(onConsume.mock.calls).toEqual([
      ['abc123', 1],
      ['abc123', 4],
    ])
    expect(screen.getByRole('button', { name: 'Finish Apples' })).toHaveTextContent('All 4')
  })

  it('"Done" finishes a measured item', () => {
    const onConsume = jest.fn()
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" onConsume={onConsume} />)

    fireEvent.click(screen.getByRole('button', { name: 'Finish Oat Milk' }))

    expect(onConsume).toHaveBeenCalledWith('abc123', 750)
  })

  it('"…" opens the sheet for any other amount', () => {
    const onMore = jest.fn()
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" onMore={onMore} />)

    fireEvent.click(screen.getByRole('button', { name: 'More for Oat Milk' }))

    expect(onMore).toHaveBeenCalledWith('abc123')
  })

  it.each(['empty', 'discarded'] as const)(
    'offers nothing to consume on a %s item, but "…" still opens it',
    (status) => {
      render(
        <InventoryItemCard
          item={{ ...MOCK_ITEM, status, current_quantity: status === 'empty' ? 0 : 750 }}
          productName="Oat Milk"
          onConsume={jest.fn()}
          onMore={jest.fn()}
        />
      )

      expect(screen.queryByRole('button', { name: /^Consume|^Finish/ })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'More for Oat Milk' })).toBeInTheDocument()
    }
  )

  it('renders no buttons when no handlers are provided', () => {
    render(<InventoryItemCard item={MOCK_ITEM} productName="Oat Milk" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Touch Targets
// ---------------------------------------------------------------------------

describe('TestInventoryItemCardTouchTargets', () => {
  it('every button on the card is at least a 44px touch target', () => {
    render(
      <InventoryItemCard
        item={MOCK_ITEM}
        productName="Oat Milk"
        onConsume={jest.fn()}
        onMore={jest.fn()}
      />
    )
    for (const button of screen.getAllByRole('button')) {
      expect(button.className).toContain('min-h-touch')
    }
  })
})

// ---------------------------------------------------------------------------
// Values the API sent that this build does not recognise (H04)
// ---------------------------------------------------------------------------

describe('TestInventoryItemCardUnknownValues', () => {
  it('renders a status it does not know instead of throwing the page away', () => {
    // StatusBadge did `statusConfig[status].variant`, and this card is on every stock row: one
    // unfamiliar status took the whole list down with it.
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, status: 'fermenting' }}
        productName="Oat Milk"
      />
    )
    expect(screen.getByText('Oat Milk')).toBeInTheDocument()
    expect(screen.getByText('fermenting')).toBeInTheDocument()
  })

  it('shows a location it does not know by its raw name', () => {
    render(
      <InventoryItemCard
        item={{ ...MOCK_ITEM, location: 'cellar' }}
        productName="Oat Milk"
        productCategory="Dairy & Eggs"
      />
    )
    expect(screen.getByText('Dairy & Eggs · cellar')).toBeInTheDocument()
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
