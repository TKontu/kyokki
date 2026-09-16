/**
 * Receipt API (MVP-R5)
 * Read receipts, confirm the reviewed lines, and queue a receipt to be read again.
 * Uploading happens through the Telegram bot; the iPad upload page is MVP-R6.
 */

import apiClient from './client'
import type {
  Receipt,
  ReceiptConfirmRequest,
  ReceiptConfirmResponse,
  ReceiptListParams,
} from '@/types/receipt'

/** Receipts, newest first. */
export async function list(params?: ReceiptListParams): Promise<Receipt[]> {
  return apiClient.get<Receipt[]>(
    '/receipts',
    params as Record<string, string | undefined> | undefined
  )
}

export async function get(id: string): Promise<Receipt> {
  return apiClient.get<Receipt>(`/receipts/${id}`)
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

const receiptsAPI = { list, get, confirm, process }
export default receiptsAPI
