/**
 * Receipt Types
 * Mirror backend schema: /backend/app/schemas/receipt.py
 */

import type { StorageType } from './product'

export type ReceiptStatus = 'uploaded' | 'processing' | 'completed' | 'failed' | 'confirmed'

/** How the receipt was read: text (PDF or OCR) or the image directly (vision model). */
export type ExtractionMethod = 'text' | 'vision'

/** Receipt quantities: weight lines in grams, everything else in pieces (volumes in dl). */
export type ReceiptUnit = 'g' | 'dl' | 'pcs'

export type MatchConfidence = 'exact' | 'high' | 'medium' | 'low'

/** alias: learned store name; exact: canonical name; fuzzy*: closest name or alias. */
export type MatchSource = 'alias' | 'exact' | 'fuzzy' | 'fuzzy_alias'

export interface ExtractedItem {
  index: number // Position on the receipt; confirm and review address items by it
  name: string // Product name as printed
  quantity: number
  unit: ReceiptUnit
  product_id: string | null // Matched product UUID
  product_name: string | null
  match_score: number | null // 0-100
  match_confidence: MatchConfidence | null
  match_source: MatchSource | null
  suggested_category: string | null // Category id
  storage_type: StorageType
  location: 'main_fridge' | 'freezer' | 'pantry'
}

export interface Receipt {
  id: string // UUID
  store_chain: string | null // Chain key (e.g. s-group) or manual value
  purchase_date: string | null // ISO date
  image_path: string // Path to receipt file
  batch_id: string | null // UUID for multi-receipt processing
  ocr_raw_text: string | null // Raw OCR or PDF text (null when read by vision)
  ocr_structured: Record<string, unknown> | null // Stored extraction (debugging)
  processing_status: ReceiptStatus
  items_extracted: number
  items_matched: number
  extraction_method: ExtractionMethod | null
  items: ExtractedItem[]
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
  processing_status?: ReceiptStatus
}

export interface ReceiptListParams {
  status?: ReceiptStatus
  store?: string
}
