'use client'

/**
 * One line on the shopping list: tap the circle to tick it bought (or untick it back), "…" to
 * remove it. Urgent, open items carry a badge; nothing else does, so the rail-tier information
 * does not repeat once the group heading already says it.
 */

import React from 'react'
import Badge from '@/components/ui/Badge'
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
  return (
    <li className="flex items-center gap-2 border-b border-ui-border py-1 last:border-b-0 dark:border-ui-dark-border">
      <button
        type="button"
        onClick={onToggle}
        aria-label={
          item.is_purchased ? `Mark ${item.name} not bought` : `Mark ${item.name} bought`
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
          {item.name}
        </p>
        <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {item.quantity} {item.unit}
        </p>
      </div>
      {!item.is_purchased && item.priority === 'urgent' && (
        <Badge variant="error" size="sm">
          Urgent
        </Badge>
      )}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${item.name}`}
        className={touchButtonClass}
      >
        <span aria-hidden="true">…</span>
      </button>
    </li>
  )
}

export default ShoppingItemRow
