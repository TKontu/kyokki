import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { InventoryList } from '../InventoryList'
import type { InventoryItem, InventoryListParams } from '@/types/inventory'

jest.mock('@/hooks/useInventory')
import { useInventoryList } from '@/hooks/useInventory'
const mockUseInventoryList = useInventoryList as jest.Mock

const MOCK_NOW = new Date('2024-02-01T12:00:00Z')

const MOCK_ITEM_A: InventoryItem = {
  id: 'item-aaa',
  product_master_id: 'prod-111',
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

const MOCK_ITEM_B: InventoryItem = {
  ...MOCK_ITEM_A,
  id: 'item-bbb',
  product_master_id: 'prod-222',
  location: 'pantry',
  status: 'sealed',
  current_quantity: 500,
  expiry_date: '2024-06-01',
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
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons).toHaveLength(3)
  })

  it('does not render item cards while loading', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    render(<InventoryList productNames={{ 'prod-111': 'Oat Milk' }} />)
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
      error: new Error('Network error'),
      data: undefined,
    })
    render(<InventoryList />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Network error')
  })

  it('renders fallback message when error has no message', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: true,
      error: null,
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
    render(<InventoryList productNames={{ 'prod-111': 'Oat Milk' }} />)
    expect(screen.queryByText('Oat Milk')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Empty
// ---------------------------------------------------------------------------

describe('TestInventoryListEmpty', () => {
  it('renders empty state message when items array is empty', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data: [] })
    render(<InventoryList />)
    expect(screen.getByText(/No items found/)).toBeInTheDocument()
  })

  it('renders suggestion to scan a product', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data: [] })
    render(<InventoryList />)
    expect(screen.getByText(/Scan a product/i)).toBeInTheDocument()
  })

  it('does not render item cards when empty', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data: [] })
    render(<InventoryList productNames={{ 'prod-111': 'Oat Milk' }} />)
    expect(screen.queryByText('Oat Milk')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('TestInventoryListRendering', () => {
  it('renders one card per item', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A, MOCK_ITEM_B],
    })
    render(<InventoryList productNames={{ 'prod-111': 'Oat Milk', 'prod-222': 'Pasta' }} />)
    expect(screen.getByText('Oat Milk')).toBeInTheDocument()
    expect(screen.getByText('Pasta')).toBeInTheDocument()
  })

  it('renders single item correctly', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    render(<InventoryList productNames={{ 'prod-111': 'Oat Milk' }} />)
    expect(screen.getByText('Oat Milk')).toBeInTheDocument()
  })

  it('falls back to truncated UUID when productNames not provided', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    render(<InventoryList />)
    expect(screen.getByText('Product prod-111')).toBeInTheDocument()
  })

  it('falls back to truncated UUID for unknown product_master_id', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    render(<InventoryList productNames={{ 'prod-999': 'Other' }} />)
    expect(screen.getByText('Product prod-111')).toBeInTheDocument()
  })

  it('uses provided product name when key matches product_master_id', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    render(<InventoryList productNames={{ 'prod-111': 'Oat Milk' }} />)
    expect(screen.getByText('Oat Milk')).toBeInTheDocument()
    expect(screen.queryByText(/Product prod/)).not.toBeInTheDocument()
  })

  it('renders items inside a list element', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    const { container } = render(<InventoryList productNames={{ 'prod-111': 'Oat Milk' }} />)
    expect(container.querySelector('ul')).toBeInTheDocument()
    expect(container.querySelector('li')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Callbacks
// ---------------------------------------------------------------------------

describe('TestInventoryListCallbacks', () => {
  it('forwards onConsume to each card', () => {
    const onConsume = jest.fn()
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    render(
      <InventoryList
        productNames={{ 'prod-111': 'Oat Milk' }}
        onConsume={onConsume}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /consume/i }))
    expect(onConsume).toHaveBeenCalledWith('item-aaa')
  })

  it('forwards onEdit to each card', () => {
    const onEdit = jest.fn()
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    render(
      <InventoryList
        productNames={{ 'prod-111': 'Oat Milk' }}
        onEdit={onEdit}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /edit/i }))
    expect(onEdit).toHaveBeenCalledWith('item-aaa')
  })

  it('renders no action buttons when no callbacks provided', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    render(<InventoryList productNames={{ 'prod-111': 'Oat Milk' }} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('calls correct item id when multiple items rendered', () => {
    const onConsume = jest.fn()
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A, MOCK_ITEM_B],
    })
    render(
      <InventoryList
        productNames={{ 'prod-111': 'Oat Milk', 'prod-222': 'Pasta' }}
        onConsume={onConsume}
      />
    )
    const buttons = screen.getAllByRole('button', { name: /consume/i })
    fireEvent.click(buttons[1])
    expect(onConsume).toHaveBeenCalledWith('item-bbb')
  })
})

// ---------------------------------------------------------------------------
// Params forwarding
// ---------------------------------------------------------------------------

describe('TestInventoryListParams', () => {
  it('forwards params to useInventoryList', () => {
    const params: InventoryListParams = { location: 'freezer', status: 'sealed' }
    mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data: [] })
    render(<InventoryList params={params} />)
    expect(mockUseInventoryList).toHaveBeenCalledWith(params)
  })

  it('calls useInventoryList with undefined when no params given', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: false, isError: false, data: [] })
    render(<InventoryList />)
    expect(mockUseInventoryList).toHaveBeenCalledWith(undefined)
  })
})

// ---------------------------------------------------------------------------
// Custom className
// ---------------------------------------------------------------------------

describe('TestInventoryListClassName', () => {
  it('applies className to list wrapper', () => {
    mockUseInventoryList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [MOCK_ITEM_A],
    })
    const { container } = render(
      <InventoryList
        productNames={{ 'prod-111': 'Oat Milk' }}
        className="my-custom-class"
      />
    )
    expect(container.querySelector('ul')?.className).toContain('my-custom-class')
  })

  it('applies className to loading wrapper', () => {
    mockUseInventoryList.mockReturnValue({ isLoading: true, isError: false, data: undefined })
    const { container } = render(<InventoryList className="my-custom-class" />)
    expect((container.firstChild as HTMLElement).className).toContain('my-custom-class')
  })
})
