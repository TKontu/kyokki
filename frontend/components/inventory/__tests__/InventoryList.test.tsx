import React from 'react'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { InventoryList } from '../InventoryList'
import type { InventoryItem, InventoryListParams } from '@/types/inventory'

jest.mock('@/hooks/useInventory')
import { useInventoryList } from '@/hooks/useInventory'
const mockUseInventoryList = useInventoryList as jest.Mock

const MOCK_NOW = new Date('2024-02-01T12:00:00Z')

// Fridge, expires in four weeks
const MOCK_ITEM_A: InventoryItem = {
  id: 'item-aaa',
  product_master_id: 'prod-111',
  product_name: 'Oat Milk',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: '🥛',
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

// Pantry, expires in four months
const MOCK_ITEM_B: InventoryItem = {
  ...MOCK_ITEM_A,
  id: 'item-bbb',
  product_master_id: 'prod-222',
  product_name: 'Pasta',
  category_name: 'Pantry Staples',
  location: 'pantry',
  status: 'sealed',
  current_quantity: 500,
  expiry_date: '2024-06-01',
}

// Fridge, expires tomorrow: pinned
const MOCK_ITEM_URGENT: InventoryItem = {
  ...MOCK_ITEM_A,
  id: 'item-urgent',
  product_master_id: 'prod-333',
  product_name: 'Minced Meat',
  category_name: 'Meat & Poultry',
  expiry_date: '2024-02-02',
}

function mockItems(data: InventoryItem[]) {
  mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data })
}

function sectionNamed(name: RegExp) {
  return screen.getByRole('region', { name })
}

beforeEach(() => {
  jest.useFakeTimers()
  jest.setSystemTime(MOCK_NOW)
  mockUseInventoryList.mockReset()
})

afterEach(() => {
  jest.useRealTimers()
})

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

describe('TestInventoryListLoading', () => {
  it('renders skeleton placeholders while loading', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    render(<InventoryList />)
    expect(screen.getByLabelText('Loading inventory')).toBeInTheDocument()
  })

  it('renders 3 skeleton divs', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    const { container } = render(<InventoryList />)
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(3)
  })

  it('does not render item cards while loading', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    render(<InventoryList />)
    expect(screen.queryByText('Oat Milk')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

describe('TestInventoryListError', () => {
  it('renders alert with error message', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error('Network failure'),
      data: undefined,
    })
    render(<InventoryList />)
    expect(screen.getByRole('alert')).toHaveTextContent('Network failure')
  })

  it('renders fallback message when error has no message', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: true,
      error: 'not an Error instance',
      data: undefined,
    })
    render(<InventoryList />)
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load inventory.')
  })

  it('does not render item cards on error', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: true,
      error: new Error('oops'),
      data: undefined,
    })
    render(<InventoryList />)
    expect(screen.queryByText('Oat Milk')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Empty and hidden items
// ---------------------------------------------------------------------------

describe('TestInventoryListEmpty', () => {
  it('renders empty state message when items array is empty', () => {
    mockItems([])
    render(<InventoryList />)
    expect(screen.getByText(/No items found/i)).toBeInTheDocument()
  })

  it('renders suggestion to scan a product', () => {
    mockItems([])
    render(<InventoryList />)
    expect(screen.getByText(/Scan a product/i)).toBeInTheDocument()
  })

  it('hides empty and discarded items', () => {
    mockItems([
      MOCK_ITEM_A,
      { ...MOCK_ITEM_B, status: 'empty', current_quantity: 0 },
      { ...MOCK_ITEM_URGENT, status: 'discarded' },
    ])
    render(<InventoryList />)
    expect(screen.getByText('Oat Milk')).toBeInTheDocument()
    expect(screen.queryByText('Pasta')).not.toBeInTheDocument()
    expect(screen.queryByText('Minced Meat')).not.toBeInTheDocument()
  })

  it('shows the empty state when only inactive items are left', () => {
    mockItems([{ ...MOCK_ITEM_A, status: 'empty', current_quantity: 0 }])
    render(<InventoryList />)
    expect(screen.getByText(/No items found/i)).toBeInTheDocument()
  })

  it('shows inactive items when include_inactive is requested', () => {
    mockItems([{ ...MOCK_ITEM_A, status: 'empty', current_quantity: 0 }])
    render(<InventoryList params={{ include_inactive: true }} />)
    expect(screen.getByText('Oat Milk')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Grouping and sorting
// ---------------------------------------------------------------------------

describe('TestInventoryListGrouping', () => {
  it('renders sections in order: expiring soon, then locations, with counts', () => {
    mockItems([MOCK_ITEM_B, MOCK_ITEM_A, MOCK_ITEM_URGENT])
    render(<InventoryList />)

    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Expiring soon1', 'Fridge1', 'Pantry1'])
  })

  it('renders a pinned item only once, in the expiring soon section', () => {
    mockItems([MOCK_ITEM_A, MOCK_ITEM_URGENT])
    render(<InventoryList />)

    expect(screen.getAllByText('Minced Meat')).toHaveLength(1)
    expect(within(sectionNamed(/Expiring soon/)).getByText('Minced Meat')).toBeInTheDocument()
    expect(within(sectionNamed(/Fridge/)).queryByText('Minced Meat')).not.toBeInTheDocument()
  })

  it('sorts items within a group by expiry, then creation time', () => {
    const later = { ...MOCK_ITEM_A, id: 'later', product_name: 'Later', expiry_date: '2024-04-01' }
    const tieNewer = {
      ...MOCK_ITEM_A,
      id: 'tie-newer',
      product_name: 'Tie Newer',
      created_at: '2024-01-03T10:00:00Z',
    }
    const tieOlder = {
      ...MOCK_ITEM_A,
      id: 'tie-older',
      product_name: 'Tie Older',
      created_at: '2024-01-02T10:00:00Z',
    }
    mockItems([later, tieNewer, tieOlder])
    render(<InventoryList />)

    const names = within(sectionNamed(/Fridge/))
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent)
    expect(names).toEqual(['Tie Older', 'Tie Newer', 'Later'])
  })

  it('omits the location from grouped cards but keeps it on pinned cards', () => {
    mockItems([MOCK_ITEM_A, MOCK_ITEM_URGENT])
    render(<InventoryList />)

    expect(within(sectionNamed(/Fridge/)).getByText('Dairy & Eggs')).toBeInTheDocument()
    expect(
      within(sectionNamed(/Expiring soon/)).getByText('Meat & Poultry · Main Fridge')
    ).toBeInTheDocument()
  })

  it('lays each section out as a two-column grid on iPad landscape', () => {
    mockItems([MOCK_ITEM_A, MOCK_ITEM_URGENT])
    render(<InventoryList />)

    for (const list of screen.getAllByRole('list')) {
      expect(list.className).toContain('grid')
      expect(list.className).toContain('lg:grid-cols-2')
    }
  })

  it('shows the category display name on the card', () => {
    mockItems([MOCK_ITEM_A])
    render(<InventoryList />)
    expect(screen.getByText('Dairy & Eggs')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Callbacks
// ---------------------------------------------------------------------------

describe('TestInventoryListCallbacks', () => {
  it('forwards onConsume to each card', () => {
    const onConsume = jest.fn()
    mockItems([MOCK_ITEM_A])
    render(<InventoryList onConsume={onConsume} />)
    fireEvent.click(screen.getByRole('button', { name: /consume/i }))
    expect(onConsume).toHaveBeenCalledWith('item-aaa')
  })

  it('forwards onEdit to each card', () => {
    const onEdit = jest.fn()
    mockItems([MOCK_ITEM_A])
    render(<InventoryList onEdit={onEdit} />)
    fireEvent.click(screen.getByRole('button', { name: /edit/i }))
    expect(onEdit).toHaveBeenCalledWith('item-aaa')
  })

  it('renders no action buttons when no callbacks provided', () => {
    mockItems([MOCK_ITEM_A])
    render(<InventoryList />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('calls the right item id from each section', () => {
    const onConsume = jest.fn()
    mockItems([MOCK_ITEM_B, MOCK_ITEM_A, MOCK_ITEM_URGENT])
    render(<InventoryList onConsume={onConsume} />)

    fireEvent.click(within(sectionNamed(/Expiring soon/)).getByRole('button', { name: /consume/i }))
    fireEvent.click(within(sectionNamed(/Pantry/)).getByRole('button', { name: /consume/i }))

    expect(onConsume.mock.calls).toEqual([['item-urgent'], ['item-bbb']])
  })
})

// ---------------------------------------------------------------------------
// Params and className
// ---------------------------------------------------------------------------

describe('TestInventoryListParams', () => {
  it('forwards params to useInventoryList', () => {
    const params: InventoryListParams = { location: 'freezer' }
    mockItems([])
    render(<InventoryList params={params} />)
    expect(mockUseInventoryList).toHaveBeenCalledWith(params)
  })

  it('calls useInventoryList with undefined when no params given', () => {
    mockItems([])
    render(<InventoryList />)
    expect(mockUseInventoryList).toHaveBeenCalledWith(undefined)
  })
})

describe('TestInventoryListClassName', () => {
  it('applies className to the wrapper when items render', () => {
    mockItems([MOCK_ITEM_A])
    const { container } = render(<InventoryList className="custom-class" />)
    expect((container.firstChild as HTMLElement).className).toContain('custom-class')
  })

  it('applies className to loading wrapper', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    const { container } = render(<InventoryList className="custom-class" />)
    expect((container.firstChild as HTMLElement).className).toContain('custom-class')
  })

  it('applies className to the empty state', () => {
    mockItems([])
    const { container } = render(<InventoryList className="custom-class" />)
    expect((container.firstChild as HTMLElement).className).toContain('custom-class')
  })
})
