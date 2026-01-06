/**
 * Receipt Types
 * Mirror backend schema: /backend/app/schemas/receipt.py
 */

export type ReceiptProcessingStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface Receipt {
  id: string // UUID
  store_chain: string | null // Store name (detected or manual)
  purchase_date: string | null // ISO date
  image_path: string // Path to receipt image
  batch_id: string | null // UUID for multi-receipt processing
  ocr_raw_text: string | null // Raw OCR output
  ocr_structured: Record<string, unknown> | null // Parsed items and metadata (JSON)
  processing_status: ReceiptProcessingStatus
  items_extracted: number // Number of items extracted (default: 0)
  items_matched: number // Number of items matched to products (default: 0)
  created_at: string // ISO datetime
}

export interface ReceiptCreate {
  store_chain?: string | null
  purchase_date?: string | null
  batch_id?: string | null
}

export interface ReceiptUpdate {
  store_chain?: string | null
  purchase_date?: string | null
  processing_status?: ReceiptProcessingStatus
}

export interface ReceiptListParams {
  status?: ReceiptProcessingStatus
  store?: string
}

// Parsed receipt data structures (from OCR/LLM extraction)
export interface ParsedProduct {
  receipt_name: string // Raw name from receipt
  matched_product_id?: string // UUID of matched product
  confidence: number // Match confidence 0-1
  quantity: number
  unit: string
  price?: number
  status: 'matched' | 'new' | 'uncertain' | 'skipped'
}

export interface StoreInfo {
  store_name: string
  store_chain: string
  country: string
  language: string
  currency: string
}

export interface ReceiptExtraction {
  store_info: StoreInfo
  purchase_date: string | null
  items: ParsedProduct[]
  total_amount: number | null
}
