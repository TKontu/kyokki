import React, { useId } from 'react'
import { useInventoryList } from '@/hooks/useInventory'
import { buildStockView } from '@/lib/stock'
import { InventoryItemCard } from './InventoryItemCard'
import type { InventoryItem, InventoryListParams } from '@/types/inventory'

export interface InventoryListProps {
  params?: InventoryListParams
  onConsume?: (id: string) => void
  onEdit?: (id: string) => void
  /** Offered beside the Expired heading. Absent means no clear is on offer. */
  onClearExpired?: (items: InventoryItem[]) => void
  className?: string
}

/**
 * The Expired section's own action.
 *
 * Deliberately a plain link-weight button rather than a danger one: it sits in a heading, and
 * the confirm is where the weight belongs - the sheet asks before anything is thrown away.
 */
function ClearExpired({
  items,
  onClear,
}: {
  items: InventoryItem[]
  onClear: (items: InventoryItem[]) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onClear(items)}
      className="ml-auto text-sm font-medium text-red-700 underline dark:text-red-400"
    >
      {`Clear ${items.length}`}
    </button>
  )
}

interface StockSectionProps {
  label: string
  items: InventoryItem[]
  /** `urgent` is the orange of "use this now"; `past` is the red of "this is compost". */
  tone?: 'plain' | 'urgent' | 'past'
  showLocation: boolean
  onConsume?: (id: string) => void
  onEdit?: (id: string) => void
  /** Rendered beside the count - the Expired section's way of offering to clear itself. */
  action?: React.ReactNode
}

const SECTION_TONES = {
  plain: {
    heading: 'text-ui-text dark:text-ui-dark-text',
    chip: 'bg-ui-bg-secondary dark:bg-ui-dark-bg-secondary border-ui-border dark:border-ui-dark-border text-ui-text-secondary dark:text-ui-dark-text-secondary',
  },
  urgent: {
    heading: 'text-orange-700 dark:text-orange-400',
    chip: 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800 text-orange-700 dark:text-orange-400',
  },
  past: {
    heading: 'text-red-700 dark:text-red-400',
    chip: 'bg-red-50 dark:bg-red-950 border-red-200 dark:border-red-800 text-red-700 dark:text-red-200',
  },
} as const

function StockSection({
  label,
  items,
  tone = 'plain',
  showLocation,
  onConsume,
  onEdit,
  action,
}: StockSectionProps) {
  const headingId = useId()
  const { heading: headingColor, chip: chipColor } = SECTION_TONES[tone]

  return (
    <section aria-labelledby={headingId}>
      <h2
        id={headingId}
        className={`mb-3 flex items-center gap-2 text-base font-semibold ${headingColor}`}
      >
        {label}
        <span className={`rounded-full border px-2 text-sm font-medium ${chipColor}`}>
          {items.length}
        </span>
        {action}
      </h2>
      <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {items.map((item) => (
          <li key={item.id}>
            <InventoryItemCard
              item={item}
              productName={item.product_name}
              productCategory={item.category_name}
              showLocation={showLocation}
              onConsume={onConsume}
              onEdit={onEdit}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

export function InventoryList({
  params,
  onConsume,
  onEdit,
  onClearExpired,
  className = '',
}: InventoryListProps) {
  const { data: items, isLoading, isError, error } = useInventoryList(params)

  if (isLoading) {
    return (
      <div className={`space-y-3 ${className}`.trim()} aria-label="Loading inventory">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700 h-32"
            aria-hidden="true"
          />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <p role="alert" className={`text-sm text-red-600 dark:text-red-400 py-4 ${className}`.trim()}>
        {error instanceof Error ? error.message : 'Failed to load inventory.'}
      </p>
    )
  }

  const { expired, expiringSoon, groups } = buildStockView(items ?? [], {
    includeInactive: params?.include_inactive === true,
  })

  if (expiringSoon.length === 0 && groups.length === 0) {
    return (
      <p
        className={`text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary py-4 ${className}`.trim()}
      >
        No items found. Scan a product to add it to your inventory.
      </p>
    )
  }

  return (
    <div className={`space-y-6 ${className}`.trim()}>
      {expired.length > 0 && (
        <StockSection
          label="Expired"
          items={expired}
          tone="past"
          showLocation
          action={onClearExpired && <ClearExpired items={expired} onClear={onClearExpired} />}
          onConsume={onConsume}
          onEdit={onEdit}
        />
      )}
      {expiringSoon.length > 0 && (
        <StockSection
          label="Expiring soon"
          items={expiringSoon}
          tone="urgent"
          showLocation
          onConsume={onConsume}
          onEdit={onEdit}
        />
      )}
      {groups.map((group) => (
        <StockSection
          key={group.key}
          label={group.label}
          items={group.items}
          showLocation={false}
          onConsume={onConsume}
          onEdit={onEdit}
        />
      ))}
    </div>
  )
}

export default InventoryList
