/**
 * Inventory API Tests
 * Using fetch mocks instead of MSW for simplicity
 */

import inventoryAPI, { normalizeInventoryItem } from '../inventory'
import type { InventoryItem, InventoryItemCreate } from '@/types/inventory'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

// Mock inventory items
const mockInventoryItem: InventoryItem = {
  id: '123e4567-e89b-12d3-a456-426614174000',
  product_master_id: '123e4567-e89b-12d3-a456-426614174001',
  product_name: 'Test Milk 1L',
  category: 'dairy',
  category_name: 'Dairy & Eggs',
  category_icon: '🥛',
  receipt_id: null,
  initial_quantity: 1000,
  current_quantity: 750,
  unit: 'dl',
  status: 'opened',
  purchase_date: '2024-01-01',
  expiry_date: '2024-01-15',
  expiry_source: 'calculated',
  opened_date: '2024-01-05',
  batch_number: null,
  location: 'main_fridge',
  notes: null,
  created_at: '2024-01-01T10:00:00Z',
  consumed_at: null,
}

const mockInventoryItems: InventoryItem[] = [
  mockInventoryItem,
  {
    ...mockInventoryItem,
    id: '123e4567-e89b-12d3-a456-426614174002',
    current_quantity: 500,
    status: 'partial',
  },
]

// Mock global fetch
global.fetch = jest.fn()

describe('Inventory API', () => {
  beforeEach(() => {
    ;(global.fetch as jest.Mock).mockClear()
  })

  describe('quantity normalization', () => {
    // Regression: the backend sends Decimal columns as strings ("1000.00"); the
    // inventory page crashed with "toFixed is not a function" on the prod stack.
    const wireItem = {
      ...mockInventoryItem,
      initial_quantity: '1000.00' as unknown as number,
      current_quantity: '750.50' as unknown as number,
    }

    it('coerces string quantities to numbers on list', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [wireItem],
      })

      const [item] = await inventoryAPI.list()
      expect(item.initial_quantity).toBe(1000)
      expect(item.current_quantity).toBe(750.5)
    })

    it('coerces string quantities on consume', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...wireItem, current_quantity: '500.00' }),
      })

      const item = await inventoryAPI.consume(mockInventoryItem.id, { quantity: 250 })
      expect(item.current_quantity).toBe(500)
      expect(typeof item.initial_quantity).toBe('number')
    })
  })

  // The four enum fields used to pass through untouched, so the screens each had to guess what
  // an unfamiliar value meant. This is now the one place that decides, and its decision is to
  // keep whatever the API said rather than substitute a default that would read as a fact (H04).
  describe('vocabulary fields', () => {
    it('keeps the values it recognises', () => {
      const item = normalizeInventoryItem(mockInventoryItem)
      expect(item.status).toBe('opened')
      expect(item.location).toBe('main_fridge')
      expect(item.unit).toBe('dl')
      expect(item.expiry_source).toBe('calculated')
    })

    it('keeps a value it does not recognise, raw', () => {
      const item = normalizeInventoryItem({
        ...mockInventoryItem,
        status: 'fermenting',
        location: 'cellar',
        unit: 'bushel',
        expiry_source: 'guessed',
      })

      expect(item.status).toBe('fermenting')
      expect(item.location).toBe('cellar')
      expect(item.unit).toBe('bushel')
      expect(item.expiry_source).toBe('guessed')
    })

    it('never substitutes a default for a missing value', () => {
      const item = normalizeInventoryItem({
        ...mockInventoryItem,
        status: null as unknown as string,
        location: undefined as unknown as string,
      })

      expect(item.status).toBe('')
      expect(item.location).toBe('')
    })

    it('runs on every response, not just the list', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...mockInventoryItem, status: 'fermenting' }),
      })

      const item = await inventoryAPI.get(mockInventoryItem.id)
      expect(item.status).toBe('fermenting')
    })
  })

  describe('list', () => {
    it('should fetch all inventory items', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockInventoryItems,
      })

      const items = await inventoryAPI.list()

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory`,
        expect.objectContaining({
          method: 'GET',
        })
      )
      expect(items).toHaveLength(2)
      expect(items[0].id).toBe(mockInventoryItem.id)
    })

    it('should send include_inactive when requested', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockInventoryItems,
      })

      await inventoryAPI.list({ include_inactive: true })

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory?include_inactive=true`,
        expect.objectContaining({ method: 'GET' })
      )
    })

    it('should filter by location', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockInventoryItems.filter(i => i.location === 'main_fridge'),
      })

      const items = await inventoryAPI.list({ location: 'main_fridge' })

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory?location=main_fridge`,
        expect.objectContaining({
          method: 'GET',
        })
      )
      expect(items).toHaveLength(2)
      expect(items.every((item) => item.location === 'main_fridge')).toBe(true)
    })
  })

  describe('get', () => {
    it('should fetch a single inventory item', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockInventoryItem,
      })

      const item = await inventoryAPI.get(mockInventoryItem.id)

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory/${mockInventoryItem.id}`,
        expect.objectContaining({
          method: 'GET',
        })
      )
      expect(item.id).toBe(mockInventoryItem.id)
      expect(item.current_quantity).toBe(750)
    })

    it('should throw error for non-existent item', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ code: 'NOT_FOUND', message: 'Item not found' }),
      })

      await expect(inventoryAPI.get('non-existent-id')).rejects.toThrow()
    })
  })

  describe('create', () => {
    it('should create a new inventory item', async () => {
      const newItemData: InventoryItemCreate = {
        product_master_id: mockInventoryItem.product_master_id,
        initial_quantity: 1000,
        current_quantity: 1000,
        unit: 'dl',
        expiry_date: '2024-02-01',
      }

      const newItem = {
        ...mockInventoryItem,
        id: '123e4567-e89b-12d3-a456-426614174099',
        ...newItemData,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => newItem,
      })

      const item = await inventoryAPI.create(newItemData)

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(newItemData),
        })
      )
      expect(item.initial_quantity).toBe(1000)
      expect(item.current_quantity).toBe(1000)
    })
  })

  describe('update', () => {
    it('should update an inventory item', async () => {
      const updateData = {
        current_quantity: 500,
        status: 'partial' as const,
      }

      const updatedItem = {
        ...mockInventoryItem,
        ...updateData,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => updatedItem,
      })

      const item = await inventoryAPI.update(mockInventoryItem.id, updateData)

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory/${mockInventoryItem.id}`,
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify(updateData),
        })
      )
      expect(item.current_quantity).toBe(500)
      expect(item.status).toBe('partial')
    })
  })

  describe('delete', () => {
    it('should delete an inventory item', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 204,
      })

      await expect(inventoryAPI.delete(mockInventoryItem.id)).resolves.toBeUndefined()

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory/${mockInventoryItem.id}`,
        expect.objectContaining({
          method: 'DELETE',
        })
      )
    })

    it('should throw error for non-existent item', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ code: 'NOT_FOUND', message: 'Item not found' }),
      })

      await expect(inventoryAPI.delete('non-existent-id')).rejects.toThrow()
    })
  })

  describe('consume', () => {
    it('should consume quantity from an inventory item', async () => {
      const consumeData = { quantity: 250 }
      const consumedItem = {
        ...mockInventoryItem,
        current_quantity: 500, // 750 - 250
        status: 'partial' as const,
      }

      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => consumedItem,
      })

      const item = await inventoryAPI.consume(mockInventoryItem.id, consumeData)

      expect(global.fetch).toHaveBeenCalledWith(
        `${API_URL}/inventory/${mockInventoryItem.id}/consume`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(consumeData),
        })
      )
      expect(item.current_quantity).toBe(500)
      expect(item.status).toBe('partial')
    })
  })
})
