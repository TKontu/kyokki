/**
 * How a receipt is named on screen. Shared by the receipts list (MVP-R8) and the review
 * page (MVP-R7), which see different shapes of the same receipt.
 */

import type { Receipt } from '@/types/receipt'

const STORE_NAMES: Record<string, string> = {
  's-group': 'S-group',
  'k-group': 'K-group',
  lidl: 'Lidl',
  tokmanni: 'Tokmanni',
}

/** The chain as a person would write it; an unknown chain keeps whatever was read. */
export function storeName(receipt: Pick<Receipt, 'store_chain'>): string {
  if (!receipt.store_chain) return 'Unknown store'
  return STORE_NAMES[receipt.store_chain] ?? receipt.store_chain
}

/** Finnish day.month.year, or a plain note when the reader did not find a date. */
export function receiptDate(receipt: Pick<Receipt, 'purchase_date'>): string {
  if (!receipt.purchase_date) return 'date not read'
  const [year, month, day] = receipt.purchase_date.split('-')
  return `${Number(day)}.${Number(month)}.${year}`
}
