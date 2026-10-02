/**
 * Receipt Types
 * Mirror backend schema: /backend/app/schemas/receipt.py
 */

import type { StorageType } from './product'
import type { Vocabulary } from './vocabulary'

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

/**
 * How a line came to point at a product.
 * alias: a learned printed name. name: a known catalog name. Both are exact keys.
 * selected: proposed rather than keyed - the row shows it as "auto". none: unresolved.
 */
export type MatchSource = 'alias' | 'name' | 'selected' | 'none'

/**
 * How a line the model's first answer left out was put back (Q27).
 * model_retry: the model read it on a second, targeted pass.
 * raw_line: the receipt line's raw text, kept as the name - no generic name and no category,
 * so the cook has to pick one.
 */
export type RecoveredBy = 'model_retry' | 'raw_line'

/**
 * How much of the receipt the read accounted for (Q27). Counts are of products, not text
 * lines, unless the name says otherwise (contract ruling 1).
 */
export interface ReceiptCompleteness {
  // Final number of product rows (model + retry + raw lines); null when read from a photo
  text_lines: number | null
  model_lines: number // Lines the model's first answer returned
  recovered_by_retry: number
  recovered_raw_lines: number
  invalid_entries: number // Entries in the model's answer that could not be used
  // After recovery: amount-bearing lines in no product row and not listed as non-products
  unaccounted_lines: number
  items_sum: number | null // What the read lines add up to
  receipt_total: number | null // The total printed on the receipt
}

export interface ExtractedItem {
  index: number // Position in the stored line list; kept for one release
  line_id: string | null // Stable identity, kept across re-reads; null before H12
  name: string // Product name as printed
  price?: number | null // The line total as printed (Q39); absent on older receipts
  generic_name: string | null // Brand-free generic name suggested for a new product
  quantity: number
  unit: ReceiptUnit
  product_id: string | null // Matched product UUID
  product_name: string | null
  match_score: number | null // 0-100
  match_confidence: MatchConfidence | null
  match_source: MatchSource | null
  verified: boolean // The mapping came from a key the cook confirmed, not a proposal
  suggested_category: string | null // Category id
  piece_grams: number | null // Roughly what one piece weighs, for produce sold by weight (Q2)
  pack_grams: number | null // Roughly what one pack weighs, for goods sold by the pack (Q8)
  shelf_life_days: number | null // Typical days it keeps; overrides the category default (Q6)
  opened_shelf_life_days: number | null // Typical days it keeps once opened (Q5)
  non_food: boolean // Household or cleaning; not offered as food (Q1)
  printed_quantity: number | null // What the receipt said, when the unit was converted
  printed_unit: string | null // Unit the receipt used, when the unit was converted
  storage_type: StorageType
  location: 'main_fridge' | 'freezer' | 'pantry'
  recovered?: RecoveredBy | null // Put back after the model missed it; absent on older receipts
}

export interface Receipt {
  id: string // UUID
  store_chain: string | null // Chain key (e.g. s-group) or manual value
  purchase_date: string | null // ISO date
  image_path: string // Path to receipt file
  batch_id: string | null // UUID for multi-receipt processing
  ocr_raw_text: string | null // Raw OCR or PDF text (null when read by vision)
  ocr_structured: Record<string, unknown> | null // Stored extraction (debugging)
  // The worker owns this value and may learn new ones without a frontend release: the chip, the
  // poll interval and the review page all have to cope with a string they do not know (H04).
  processing_status: Vocabulary<ReceiptStatus>
  error: string | null // Last processing failure, if any
  queued_at: string | null // ISO datetime it entered the queue
  processing_started_at: string | null // ISO datetime the worker started reading it
  items_extracted: number
  items_matched: number
  extraction_method: ExtractionMethod | null
  fallback_reason: string | null // Why the heuristic parser was used instead of the model
  items: ExtractedItem[]
  // Null or absent for older receipts; a photo receipt has one with text_lines null (Q27)
  completeness?: ReceiptCompleteness | null
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
  index?: number | null // Receipt line by position
  line_id?: string | null // Receipt line by identity; wins over index
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
  non_food_indexes?: number[] // Lines the cook says are not food; remembered (Q1)
}

export interface ReceiptConfirmResponse {
  success: boolean
  items_created: number
  products_created: number
  aliases_learned: number
  error: string | null
}

/**
 * Which receipt line an inventory item was confirmed from (Q26).
 * `GET /api/inventory/{item_id}/source`; null when the item has no receipt. `line_text` and
 * `line_index` are null for an item confirmed before this was tracked, or one added by hand.
 */
export interface ItemSource {
  receipt_id: string
  store_chain: string | null
  purchase_date: string | null
  line_text: string | null
  line_index: number | null
}

/**
 * How a printed receipt line's outcome reads on the audit view (Q28). `pending`: not
 * confirmed yet. `stocked`: it became one or more inventory items. `household`: folded away
 * as non-food. `skipped`: neither - the cook left it out. `removed`: it was stocked at
 * confirm, but every item it produced has since been hard-deleted (audit follow-up).
 */
export type ReceiptLineOutcome = 'pending' | 'stocked' | 'household' | 'skipped' | 'removed'

/** One inventory item a receipt (or receipt line) produced. */
export interface ReceiptAuditItemRef {
  id: string
  product_id: string | null
  product_name: string | null
}

/** One printed receipt line and what became of it (Q28). */
export interface ReceiptAuditLine {
  index: number
  name: string
  price: number | null
  outcome: ReceiptLineOutcome
  items: ReceiptAuditItemRef[] // Set when outcome is 'stocked'
  reanalysed?: boolean // The cook asked the model again for this line alone (Q38)
  reanalyse_hint?: string | null // The cook's hint on the re-analyse that last touched it
}

/**
 * `POST /api/receipts/{id}/lines/{line_id}/reanalyse` (Q38): re-ask the model for one
 * line's generic name, category and match, with the cook's optional hint. Nothing is
 * learned - no alias, synonym or product is created or changed.
 */
export interface ReanalyseLineRequest {
  hint?: string | null
}

/**
 * Everything the cook can check about how a receipt became stock (Q28).
 * `GET /api/receipts/{id}/audit`, for any processing status. The original file is served
 * separately at `GET /api/receipts/{id}/file`.
 */
export interface ReceiptAudit {
  id: string
  store_chain: string | null
  purchase_date: string | null
  processing_status: Vocabulary<ReceiptStatus>
  created_at: string
  ocr_raw_text: string | null
  model_raw_answer: string | null // The model's raw completion, when one was stored (#131)
  // The targeted re-read's raw completion (Q27), when the first read missed lines
  model_raw_answer_retry: string | null
  // What GET /file would serve; null if the stored file is gone - tells the viewer whether
  // to render an <img> or a PDF viewer
  file_content_type: string | null
  lines: ReceiptAuditLine[]
  // Items created from this receipt before its line index was tracked (no backfill, Q26)
  unlinked_items: ReceiptAuditItemRef[]
}
