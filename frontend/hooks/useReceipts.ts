/**
 * useReceipts (MVP-R5)
 * Receipt queries that follow a receipt while the worker reads it, and the confirm mutation.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { inventoryKeys } from '@/hooks/useInventory'
import { productKeys } from '@/hooks/useProducts'
import receiptsAPI from '@/lib/api/receipts'
import type { Receipt, ReceiptConfirmRequest, ReceiptListParams } from '@/types/receipt'

/** Poll this often while a receipt is queued or being read; extraction takes ~40-70 s. */
export const READING_POLL_MS = 3000
/** Poll the list this often when nothing is being read. */
export const IDLE_POLL_MS = 30000

export const receiptKeys = {
  all: ['receipts'] as const,
  lists: () => [...receiptKeys.all, 'list'] as const,
  list: (params?: ReceiptListParams) => [...receiptKeys.lists(), params] as const,
  details: () => [...receiptKeys.all, 'detail'] as const,
  detail: (id: string) => [...receiptKeys.details(), id] as const,
}

/** Queued or processing: the worker still has it. */
export function isBeingRead(receipt: Pick<Receipt, 'processing_status'>): boolean {
  return receipt.processing_status === 'queued' || receipt.processing_status === 'processing'
}

/** Poll one receipt only while it is being read; stop once it is finished. */
export function detailPollInterval(receipt?: Receipt): number | false {
  return receipt && isBeingRead(receipt) ? READING_POLL_MS : false
}

/** The list keeps a slow heartbeat, and speeds up while any receipt is being read. */
export function listPollInterval(receipts?: Receipt[]): number {
  return receipts?.some(isBeingRead) ? READING_POLL_MS : IDLE_POLL_MS
}

/** One receipt; polls while the worker reads it and stops once it is finished. */
export function useReceipt(id: string) {
  return useQuery({
    queryKey: receiptKeys.detail(id),
    queryFn: () => receiptsAPI.get(id),
    enabled: Boolean(id),
    refetchInterval: (query) => detailPollInterval(query.state.data),
  })
}

/** Receipts for the home banner; polls faster while one is being read. */
export function useReceiptList(params?: ReceiptListParams) {
  return useQuery({
    queryKey: receiptKeys.list(params),
    queryFn: () => receiptsAPI.list(params),
    refetchInterval: (query) => listPollInterval(query.state.data),
  })
}

/** Confirm the reviewed lines; the response says how much stock was created. */
export function useConfirmReceipt() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ReceiptConfirmRequest }) =>
      receiptsAPI.confirm(id, data),
    // Confirming is not idempotent: a retry after a lost response would double the stock.
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventoryKeys.lists() })
      queryClient.invalidateQueries({ queryKey: receiptKeys.all })
      // Confirming may have created products that searches should now find
      queryClient.invalidateQueries({ queryKey: productKeys.all })
    },
  })
}

/** Queue a failed or heuristic receipt for the model again. */
export function useReprocessReceipt() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => receiptsAPI.process(id),
    retry: false,
    onSuccess: (receipt) => {
      queryClient.setQueryData(receiptKeys.detail(receipt.id), receipt)
      queryClient.invalidateQueries({ queryKey: receiptKeys.all })
    },
  })
}
