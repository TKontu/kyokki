/**
 * The product name to show in the cook's chosen display language (Post-MVP frontier item 13).
 *
 * `display_names` (on a product) and `product_display_names` (on an inventory item, mirroring
 * `product_emoji`'s own derived-field pattern) carry a name per language, cook-set or
 * model-proposed; English is never a key in that map; it is always `canonical_name` /
 * `product_name`. A language with no entry - including English itself - falls back to it.
 *
 * Never used for receipt text: the printed line on the review and audit screens is untouched
 * by this lane (the operator's own ruling, 2026-10-02).
 */

import type { Language } from './language'

export function displayName(
  names: Record<string, string> | null | undefined,
  canonicalName: string,
  language: Language
): string {
  if (language === 'en') return canonicalName
  const named = names?.[language]
  return named && named.trim() !== '' ? named : canonicalName
}
