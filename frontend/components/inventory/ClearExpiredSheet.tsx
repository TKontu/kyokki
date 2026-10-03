'use client'

/**
 * Throwing away a shelf of expired food, in one tap and with a way back.
 *
 * Expired items used to pin themselves to the top of the stock list forever - there was no
 * lower bound on "expiring soon" - and the only way out was Edit → Mark as gone, one at a time.
 * On a wall display after a stale receipt that buries everything still edible.
 *
 * **It records them as thrown away**, and says so before it does: the eaten-versus-wasted
 * distinction is the number this whole app exists to reduce, and clearing them as anything
 * else would hide exactly the waste the cook is trying to see.
 */

import React from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { useBulkInventoryMove } from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { formatExpiryDate } from '@/lib/dates'
import { displayName } from '@/lib/displayName'
import { useT } from '@/lib/i18n'
import { useLanguage } from '@/lib/language'
import type { InventoryItem } from '@/types/inventory'

export interface ClearExpiredSheetProps {
  items: InventoryItem[]
  open: boolean
  onClose: () => void
}

function errorText(error: unknown, fallback: string): string {
  return isAPIError(error) && error.status < 500 && error.message ? error.message : fallback
}

export function ClearExpiredSheet({ items, open, onClose }: ClearExpiredSheetProps) {
  const move = useBulkInventoryMove()
  const toast = useToast()
  const [language] = useLanguage()
  const { t } = useT()

  if (!open || items.length === 0) return null

  const count = items.length
  const ids = items.map((item) => item.id)

  const clear = () => {
    move.mutate(
      { ids, event: 'discard' },
      {
        onSuccess: (result) => {
          // The header's Undo takes the whole shelf back as one step
          toast.success(t('inventory.clearExpired.toast', { count: result.changed }))
          onClose()
        },
        onError: (error) =>
          toast.error(
            errorText(error, t('inventory.clearExpired.error', { count }))
          ),
      }
    )
  }

  return (
    <BottomSheet
      open
      onClose={onClose}
      title={t('inventory.clearExpired.title', { count })}
      footer={
        <div className="grid grid-cols-2 gap-3">
          {/* Throwing a shelf away is the destructive one; focus stays on the way out (H45) */}
          <Button data-primary variant="secondary" size="lg" disabled={move.isPending} onClick={onClose}>
            {t('inventory.clearExpired.cancel')}
          </Button>
          <Button
            variant="danger"
            size="lg"
            loading={move.isPending}
            onClick={clear}
          >
            {t('inventory.clearExpired.confirm')}
          </Button>
        </div>
      }
    >
      <p className="text-base text-ui-text dark:text-ui-dark-text">
        {t('inventory.clearExpired.body')}
      </p>
      <ul className="mt-4 flex flex-col gap-1">
        {items.map((item) => (
          <li
            key={item.id}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <span className="truncate text-ui-text dark:text-ui-dark-text">
              {displayName(item.product_display_names, item.product_name, language)}
            </span>
            <span className="shrink-0 text-ui-text-secondary dark:text-ui-dark-text-secondary">
              {formatExpiryDate(item.expiry_date)}
            </span>
          </li>
        ))}
      </ul>
    </BottomSheet>
  )
}

export default ClearExpiredSheet
