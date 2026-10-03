'use client'

/**
 * One line on the shopping list: tap the circle to tick it bought (or untick it back), "…" to
 * remove it. An item the kitchen added itself (A1, below its minimum stock) carries a small
 * "Auto" marker - an icon plus the word, never colour alone, so it reads in black and white too.
 * Urgent, open items also carry a badge; nothing else does, so the rail-tier information does
 * not repeat once the group heading already says it.
 */

import React from 'react'
import Badge from '@/components/ui/Badge'
import { displayName } from '@/lib/displayName'
import { useT } from '@/lib/i18n'
import { useLanguage } from '@/lib/language'
import type { ShoppingListItem } from '@/types/shopping'

export interface ShoppingItemRowProps {
  item: ShoppingListItem
  onToggle: () => void
  onRemove: () => void
}

const touchButtonClass =
  'flex min-h-touch min-w-touch items-center justify-center rounded-ui no-select ' +
  'text-ui-text-secondary hover:bg-ui-bg-secondary dark:text-ui-dark-text-secondary ' +
  'dark:hover:bg-ui-dark-bg-secondary focus:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-primary-500'

export function ShoppingItemRow({ item, onToggle, onRemove }: ShoppingItemRowProps) {
  const [language] = useLanguage()
  const { t } = useT()
  // Post-MVP frontier item 13, phase 2: `product_display_names` is empty for a free-text
  // item, a product with no name in this language, or - deliberately, the backend's own
  // guard - a row the cook has retyped away from the product's canonical name, so
  // `displayName()` falls back to `name` exactly as typed in every one of those cases.
  const name = displayName(item.product_display_names, item.name, language)
  return (
    <li className="flex items-center gap-2 border-b border-ui-border py-1 last:border-b-0 dark:border-ui-dark-border">
      <button
        type="button"
        onClick={onToggle}
        aria-label={
          item.is_purchased
            ? t('shopping.itemRow.markNotBought', { name })
            : t('shopping.itemRow.markBought', { name })
        }
        className={`${touchButtonClass} text-xl`}
      >
        <span aria-hidden="true">{item.is_purchased ? '✅' : '⬜'}</span>
      </button>
      <div className="min-w-0 flex-1">
        <p
          className={`truncate font-medium text-ui-text dark:text-ui-dark-text ${
            item.is_purchased ? 'text-ui-text-secondary line-through dark:text-ui-dark-text-secondary' : ''
          }`}
        >
          {name}
        </p>
        <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {item.quantity} {item.unit}
        </p>
      </div>
      {item.source === 'auto_restock' && (
        <Badge variant="info" size="sm">
          <span aria-hidden="true">🔁</span> {t('shopping.itemRow.auto')}
        </Badge>
      )}
      {!item.is_purchased && item.priority === 'urgent' && (
        <Badge variant="error" size="sm">
          {t('shopping.itemRow.urgent')}
        </Badge>
      )}
      <button
        type="button"
        onClick={onRemove}
        aria-label={t('shopping.itemRow.remove', { name })}
        className={touchButtonClass}
      >
        <span aria-hidden="true">…</span>
      </button>
    </li>
  )
}

export default ShoppingItemRow
