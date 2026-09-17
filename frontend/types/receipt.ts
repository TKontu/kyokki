/**
 * Receipt Types
 * Mirror backend schema: /backend/app/schemas/receipt.py
 */

import type { StorageType } from './product'

/** Uploads are queued and read by the worker service; 'uploaded' only on pre-queue receipts. */
export type ReceiptStatus =
  | 'uploaded'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'confirmed'

/** How the receipt was read: text (PDF or OCR) or the image directly (vision model). */
export type ExtractionMethod = 'text' | 'vision' | 'heuristic'

/** Receipt quantities: weight lines in grams, everything else in pieces (volumes in dl). */
export type ReceiptUnit = 'g' | 'dl' | 'pcs'

export type MatchConfidence = 'exact' | 'high' | 'medium' | 'low'

/** alias: learned store name; exact: canonical name; fuzzy*: closest name or alias. */
export type MatchSource = 'alias' | 'exact' | 'fuzzy' | 'fuzzy_alias'

export interface ExtractedItem {
  index: number // Position on the receipt; confirm and review address items by it
  name: string // Product name as printed
  generic_name: string | null // Brand-free generic name suggested for a new product
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
  error: string | null // Last processing failure, if any
  queued_at: string | null // ISO datetime it entered the queue
  processing_started_at: string | null // ISO datetime the worker started reading it
  items_extracted: number
  items_matched: number
  extraction_method: ExtractionMethod | null
  fallback_reason: string | null // Why the heuristic parser was used instead of the model
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

/**
 * One receipt as the list returns it (MVP-R8). The list is polled, so the API leaves out the
 * OCR text, the stored extraction and the items; open a receipt to get those.
 */
export type ReceiptSummary = Omit<
  Receipt,
  'image_path' | 'batch_id' | 'ocr_raw_text' | 'ocr_structured' | 'items'
>

export interface ReceiptListParams {
  status?: ReceiptStatus
  store?: string
  limit?: number
  offset?: number
}

/**
 * One reviewed receipt item. Give product_id for an existing product; otherwise a generic
 * product is reused by name or created (name and category default to the receipt line).
 * index names the receipt line so its printed name is learned as a store alias.
 * At least one of product_id, name or index is required.
 */
export interface ConfirmedItemCreate {
  index?: number | null
  product_id?: string | null
  name?: string | null
  category?: string | null
  quantity: number
  unit: string // dl, tsp, tbsp, g, pcs (ml, l, kg, kpl convert on write)
  purchase_date: string // ISO date
  expiry_date?: string | null // Override; default purchase date + shelf life
  location?: 'main_fridge' | 'freezer' | 'pantry' | null // Override; default from storage type
}

export interface ReceiptConfirmRequest {
  items: ConfirmedItemCreate[] // Lines not sent are skipped
}

export interface ReceiptConfirmResponse {
  success: boolean
  items_created: number
  products_created: number
  aliases_learned: number
  error: string | null
}
