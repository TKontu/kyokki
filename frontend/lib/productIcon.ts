/**
 * One precedence rule for every product icon (Q18 build, operator ruling 2026-09-27).
 *
 * A tile or the product editor shows the first of these that exists:
 *   1. the exact Apple emoji - `product_emoji` on a tile (already gated server-side), or
 *      `emoji` on a product when `emoji_match` is `exact` or `cook`;
 *   2. the drawn icon (Q18, unchanged): a version means there is a drawing to show;
 *   3. the category emoji.
 *
 * A `proposed` emoji is never shown here - it is not exact until a person confirms it
 * (`docs/spikes/Q18_exact_emoji.md`, "Operator rulings").
 */

import type { EmojiMatch } from '@/types/product'

export interface ProductIconInput {
  /** The candidate emoji: `product_emoji` on a tile, or `emoji` on a product. */
  emoji: string | null | undefined
  /**
   * Gates `emoji` on a product: shown only for `exact` or `cook`. Omit it for a tile's
   * `product_emoji`, which the API has already gated the same way - any value it sends is
   * shown.
   */
  emojiMatch?: EmojiMatch | null
  /** The product's drawn icon version (Q18), or null/undefined when there is none. */
  iconVersion: number | null | undefined
  /** The category's emoji, the last resort. */
  categoryIcon: string | null | undefined
}

export type ProductIcon =
  | { kind: 'emoji'; value: string }
  | { kind: 'drawn'; version: number }
  | { kind: 'category'; value: string }
  | { kind: 'none' }

const EMOJI_SHOWN: EmojiMatch[] = ['exact', 'cook']

/** The one icon to show, in precedence order. */
export function resolveProductIcon(input: ProductIconInput): ProductIcon {
  const { emojiMatch } = input
  const gated = emojiMatch === undefined || (emojiMatch !== null && EMOJI_SHOWN.includes(emojiMatch))
  if (input.emoji && gated) {
    return { kind: 'emoji', value: input.emoji }
  }
  if (input.iconVersion !== null && input.iconVersion !== undefined) {
    return { kind: 'drawn', version: input.iconVersion }
  }
  if (input.categoryIcon) {
    return { kind: 'category', value: input.categoryIcon }
  }
  return { kind: 'none' }
}

/** The plain glyph to render when the icon is not a drawing (an emoji, category, or ''). */
export function productIconGlyph(icon: ProductIcon, categoryIcon: string | null | undefined) {
  if (icon.kind === 'emoji' || icon.kind === 'category') return icon.value
  return categoryIcon ?? ''
}
