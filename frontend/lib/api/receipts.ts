/**
 * Receipt API (MVP-R5, upload added in MVP-R6)
 * Read receipts, upload one from the iPad, confirm the reviewed lines, and queue a receipt to
 * be read again. Receipts also arrive through the Telegram bot.
 */

import apiClient, { API_BASE_URL } from './client'
import type {
  Receipt,
  ReceiptAudit,
  ReceiptConfirmRequest,
  ReceiptConfirmResponse,
  ReceiptListParams,
  ReceiptSummary,
} from '@/types/receipt'

/** What the upload form can say about a receipt the reader cannot work out itself. */
export interface ReceiptScanFields {
  store_chain?: string
  purchase_date?: string
}

/** Receipts, newest first. Summaries: no OCR text and no items. */
export async function list(params?: ReceiptListParams): Promise<ReceiptSummary[]> {
  return apiClient.get<ReceiptSummary[]>(
    '/receipts',
    params as Record<string, string | number | undefined> | undefined
  )
}

export async function get(id: string): Promise<Receipt> {
  return apiClient.get<Receipt>(`/receipts/${id}`)
}

/**
 * Everything the cook can check about how a receipt became stock (Q28): the OCR text, the
 * model's raw answer when stored, and each printed line's outcome. Works for any status.
 */
export async function audit(id: string): Promise<ReceiptAudit> {
  return apiClient.get<ReceiptAudit>(`/receipts/${id}/audit`)
}

/**
 * Where the receipt's original image or PDF is served (Q28), for an `<img src>` or an
 * `<iframe>`/`<object>`. Never fetch this into the DOM as markup.
 */
export function fileUrl(id: string): string {
  return `${API_BASE_URL}/receipts/${encodeURIComponent(id)}/file`
}

/** Turn the reviewed lines into stock. Lines left out are skipped. */
export async function confirm(
  id: string,
  data: ReceiptConfirmRequest
): Promise<ReceiptConfirmResponse> {
  return apiClient.post<ReceiptConfirmResponse>(`/receipts/${id}/confirm`, data)
}

/** Queue a failed (or heuristic) receipt for the model again. */
export async function process(id: string): Promise<Receipt> {
  // No body: the endpoint only re-queues the receipt
  return apiClient.post<Receipt>(`/receipts/${id}/process`, undefined)
}

/** Upload a receipt from the iPad. It comes back already queued for the worker. */
export async function scan(file: File, fields?: ReceiptScanFields): Promise<Receipt> {
  const data: Record<string, string> = {}
  if (fields?.store_chain) data.store_chain = fields.store_chain
  if (fields?.purchase_date) data.purchase_date = fields.purchase_date
  return apiClient.upload<Receipt>('/receipts/scan', file, data)
}

const receiptsAPI = { list, get, audit, fileUrl, confirm, process, scan }
export default receiptsAPI
