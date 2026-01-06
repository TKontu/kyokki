import {
  type InventoryItem,
  type ProductMaster,
  type Category,
  type Receipt,
  APIError,
  NetworkError,
  isAPIError,
  isNetworkError,
} from '../index'

describe('TypeScript Types', () => {
  describe('Type Compilation', () => {
    it('should compile InventoryItem type', () => {
      const item: InventoryItem = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        product_master_id: '123e4567-e89b-12d3-a456-426614174001',
        receipt_id: null,
        initial_quantity: 1000,
        current_quantity: 750,
        unit: 'ml',
        status: 'opened',
        purchase_date: '2024-01-01',
        expiry_date: '2024-01-15',
        expiry_source: 'calculated',
        opened_date: '2024-01-05',
        batch_number: null,
        location: 'main_fridge',
        notes: null,
        created_at: '2024-01-01T00:00:00Z',
        consumed_at: null,
      }
      expect(item.id).toBeDefined()
    })

    it('should compile ProductMaster type', () => {
      const product: ProductMaster = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        canonical_name: 'Milk',
        category: 'dairy',
        storage_type: 'refrigerator',
        default_shelf_life_days: 7,
        opened_shelf_life_days: 3,
        unit_type: 'volume',
        default_unit: 'ml',
        default_quantity: 1000,
        min_stock_quantity: 1000,
        reorder_quantity: 2000,
        off_product_id: null,
        off_data: null,
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      }
      expect(product.id).toBeDefined()
    })

    it('should compile Category type', () => {
      const category: Category = {
        id: 'dairy',
        display_name: 'Dairy Products',
        icon: '🥛',
        default_shelf_life_days: 7,
        meal_contexts: ['breakfast', 'lunch'],
        sort_order: 0,
      }
      expect(category.id).toBeDefined()
    })

    it('should compile Receipt type', () => {
      const receipt: Receipt = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        store_chain: 'S-Market',
        purchase_date: '2024-01-01',
        image_path: '/receipts/receipt-123.jpg',
        batch_id: null,
        ocr_raw_text: null,
        ocr_structured: null,
        processing_status: 'queued',
        items_extracted: 0,
        items_matched: 0,
        created_at: '2024-01-01T00:00:00Z',
      }
      expect(receipt.id).toBeDefined()
    })
  })

  describe('Type Guards', () => {
    it('should identify APIError correctly', () => {
      const error = new APIError(404, 'NOT_FOUND', 'Resource not found')
      expect(isAPIError(error)).toBe(true)
      expect(isNetworkError(error)).toBe(false)
    })

    it('should identify NetworkError correctly', () => {
      const error = new NetworkError('Connection failed')
      expect(isNetworkError(error)).toBe(true)
      expect(isAPIError(error)).toBe(false)
    })

    it('should reject non-error objects', () => {
      const notAnError = { message: 'Not an error' }
      expect(isAPIError(notAnError)).toBe(false)
      expect(isNetworkError(notAnError)).toBe(false)
    })
  })

  describe('APIError', () => {
    it('should create APIError with all properties', () => {
      const error = new APIError(400, 'VALIDATION_ERROR', 'Invalid input', {
        field: 'email',
      })
      expect(error.status).toBe(400)
      expect(error.code).toBe('VALIDATION_ERROR')
      expect(error.message).toBe('Invalid input')
      expect(error.details).toEqual({ field: 'email' })
      expect(error.name).toBe('APIError')
    })
  })

  describe('NetworkError', () => {
    it('should create NetworkError with default message', () => {
      const error = new NetworkError()
      expect(error.message).toBe('Network request failed')
      expect(error.name).toBe('NetworkError')
    })

    it('should create NetworkError with custom message', () => {
      const error = new NetworkError('Timeout')
      expect(error.message).toBe('Timeout')
    })
  })
})
