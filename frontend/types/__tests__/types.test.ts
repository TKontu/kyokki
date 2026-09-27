import {
  type InventoryItem,
  type ProductMaster,
  type Category,
  type ExtractedItem,
  type Receipt,
  APIError,
  NetworkError,
  isAPIError,
  isNetworkError,
} from '../index'
import type { IconRedrawRequest, IconStatus } from '../product'

describe('TypeScript Types', () => {
  describe('Type Compilation', () => {
    it('should compile InventoryItem type', () => {
      const item: InventoryItem = {
        id: '123e4567-e89b-12d3-a456-426614174000',
        product_master_id: '123e4567-e89b-12d3-a456-426614174001',
        product_name: 'Milk',
        category: 'dairy',
        category_name: 'Dairy & Eggs',
        category_icon: null,
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
        created_at: '2024-01-01T00:00:00Z',
        consumed_at: null,
        opened_shelf_life_days: null,
        avg_piece_grams: null,
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
        frozen_shelf_life_days: null,
    avg_piece_grams: null,
  pack_grams: null,
  shelf_life_source: 'category',
        unit_type: 'volume',
        default_unit: 'dl',
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

    it('should carry the drawn icon fields (Q18)', () => {
      const status: IconStatus[] = ['pending', 'ready', 'failed', 'cleared']
      const product: Pick<ProductMaster, 'icon_status' | 'icon_version'> = {
        icon_status: 'ready',
        icon_version: 1790000000,
      }
      const item: Pick<InventoryItem, 'product_icon_version'> = { product_icon_version: null }
      const redraw: IconRedrawRequest = { hint: 'oval rye pastry' }
      expect(status).toHaveLength(4)
      expect(product.icon_version).toBe(1790000000)
      expect(item.product_icon_version).toBeNull()
      expect(redraw.hint).toBe('oval rye pastry')
    })

    it('should compile Category type', () => {
      const category: Category = {
        id: 'dairy',
        display_name: 'Dairy Products',
        icon: '🥛',
        default_shelf_life_days: 7,
        frozen_shelf_life_days: null,
        sort_order: 0,
        default_storage: 'refrigerator',
        shelf_life_min_days: 1,
        shelf_life_max_days: 60,
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
        processing_status: 'completed',
        error: null,
        queued_at: '2024-01-01T10:00:00Z',
        processing_started_at: '2024-01-01T10:00:02Z',
        items_extracted: 1,
        items_matched: 1,
        extraction_method: 'vision',
        fallback_reason: null,
        items: [
          {
            index: 0,
            line_id: '123e4567-e89b-12d3-a456-426614174099',
            name: 'PUNASIPULI',
            generic_name: 'Red onion',
            quantity: 330,
            unit: 'g',
            product_id: '123e4567-e89b-12d3-a456-426614174001',
            product_name: 'Punasipuli',
            match_score: 100,
            match_confidence: 'exact',
            match_source: 'alias',
            verified: true,
            suggested_category: 'produce',
            piece_grams: 110,
            pack_grams: 500,
            shelf_life_days: 30,
            opened_shelf_life_days: null,
            non_food: false,
            printed_quantity: null,
            printed_unit: null,
            storage_type: 'refrigerator',
            location: 'main_fridge',
          },
        ],
        created_at: '2024-01-01T00:00:00Z',
      }
      expect(receipt.items[0].unit).toBe('g')
    })

    it('should carry how a line was recovered and the read completeness (Q27)', () => {
      const item: ExtractedItem = {
        index: 7,
        line_id: null,
        name: 'KG BANAANI',
        generic_name: null,
        quantity: 1200,
        unit: 'g',
        product_id: null,
        product_name: null,
        match_score: null,
        match_confidence: null,
        match_source: null,
        verified: false,
        suggested_category: null,
        piece_grams: null,
        pack_grams: null,
        shelf_life_days: null,
        opened_shelf_life_days: null,
        non_food: false,
        printed_quantity: null,
        printed_unit: null,
        storage_type: 'refrigerator',
        location: 'main_fridge',
        recovered: 'raw_line',
      }
      const completeness: Receipt['completeness'] = {
        text_lines: 15,
        model_lines: 6,
        recovered_by_retry: 8,
        recovered_raw_lines: 1,
        invalid_entries: 2,
        unaccounted_lines: 0,
        items_sum: 42.1,
        receipt_total: 42.1,
      }
      // A photo receipt has no text to count lines in; only the arithmetic applies
      const photo: Receipt['completeness'] = { ...completeness, text_lines: null }
      const retried: ExtractedItem['recovered'] = 'model_retry'
      // Older receipts carry neither field
      const older: ExtractedItem['recovered'] = null
      expect(item.recovered).toBe('raw_line')
      expect(completeness?.text_lines).toBe(15)
      expect(photo?.text_lines).toBeNull()
      expect([retried, older]).toEqual(['model_retry', null])
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
