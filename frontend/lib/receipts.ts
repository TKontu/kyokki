/**
 * How a receipt is named on screen. Shared by the receipts list (MVP-R8) and the review
 * page (MVP-R7), which see different shapes of the same receipt.
 *
 * `storeName`/`receiptDate`/`readMethod` take an optional `Language` (Post-MVP frontier item
 * 13, phase 3, round 2026-10-03-3), the same no-hooks pattern as `lib/dates.ts` and
 * `lib/fridge.ts`'s `areaLabel`: the caller (already holding `useT()`) passes the language in,
 * defaulting to `'en'` so every existing caller - including `components/inventory/ItemEditSheet.tsx`,
 * out of scope this phase - keeps its English output untouched. The chain names in
 * `STORE_NAMES` and the `d.m.yyyy` date shape are proper nouns and a locale-neutral format
 * respectively, not translated.
 */

import type { Language } from './language'
import type { Receipt } from '@/types/receipt'

const STORE_NAMES: Record<string, string> = {
  's-group': 'S-group',
  'k-group': 'K-group',
  lidl: 'Lidl',
  tokmanni: 'Tokmanni',
}

/** The chain as a person would write it; an unknown chain keeps whatever was read. */
export function storeName(
  receipt: Pick<Receipt, 'store_chain'>,
  language: Language = 'en'
): string {
  if (!receipt.store_chain) return language === 'fi' ? 'Tuntematon kauppa' : 'Unknown store'
  return STORE_NAMES[receipt.store_chain] ?? receipt.store_chain
}

/** Day.month.year (the same shape in both languages), or a plain note when the reader did
 * not find a date. */
export function receiptDate(
  receipt: Pick<Receipt, 'purchase_date'>,
  language: Language = 'en'
): string {
  if (!receipt.purchase_date) return language === 'fi' ? 'päivää ei luettu' : 'date not read'
  const [year, month, day] = receipt.purchase_date.split('-')
  return `${Number(day)}.${Number(month)}.${year}`
}

/**
 * How this receipt was read, in one short phrase (Q9).
 *
 * `heuristic` means the model never ran: no categories, no generic names, no per-product
 * estimates - and the receipt still reports `completed`. That was visible in exactly one
 * place, the review screen, and only for the bad value, so a good read and "nobody looked"
 * were indistinguishable from the list. Now every receipt says which it was.
 *
 * `null` is not a method: a receipt that has not been read yet has nothing to say.
 */
export function readMethod(
  receipt: Pick<Receipt, 'extraction_method'>,
  language: Language = 'en'
): { label: string; ok: boolean } | null {
  if (language === 'fi') {
    switch (receipt.extraction_method) {
      case 'text':
        return { label: 'luettu mallilla', ok: true }
      case 'vision':
        return { label: 'luettu mallilla kuvasta', ok: true }
      case 'heuristic':
        return { label: 'luettu ilman mallia', ok: false }
      default:
        return null
    }
  }
  switch (receipt.extraction_method) {
    case 'text':
      return { label: 'read by the model', ok: true }
    case 'vision':
      return { label: 'read by the model from the image', ok: true }
    case 'heuristic':
      return { label: 'read without the model', ok: false }
    default:
      return null
  }
}

/**
 * A receipt old enough that its items will land already expired (Q10).
 *
 * Expiry is `purchase_date + shelf life` - counted from the shop, never from the day of
 * adding - which is right, and which means a receipt from three months ago quietly adds
 * fifteen expired items. Keyed on the receipt date rather than per-item expiry on purpose:
 * the client does not know a matched product's stored shelf life, only the model's guess
 * for the line, so a per-item prediction would be wrong exactly when it mattered.
 */
export const STALE_AFTER_DAYS = 14

export function receiptAgeDays(
  receipt: Pick<Receipt, 'purchase_date'>,
  today: Date = new Date()
): number | null {
  if (!receipt.purchase_date) return null
  const [year, month, day] = receipt.purchase_date.split('-').map(Number)
  if (!year || !month || !day) return null
  // Both dates are pinned to UTC midnight before subtracting. Subtracting wall-clock
  // times instead loses a day across a spring clock change: 23 calendar days become
  // 22.958, and `Math.floor` turns a fortnight-and-a-half-old receipt into one day
  // younger than it is. Only calendar days matter here.
  const purchased = Date.UTC(year, month - 1, day)
  if (Number.isNaN(purchased)) return null
  const midnight = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.round((midnight - purchased) / 86_400_000)
}

export function isStale(
  receipt: Pick<Receipt, 'purchase_date'>,
  today: Date = new Date()
): boolean {
  const age = receiptAgeDays(receipt, today)
  return age !== null && age > STALE_AFTER_DAYS
}
