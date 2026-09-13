import React, { useId } from 'react'
import { useInventoryList } from '@/hooks/useInventory'
import { buildStockView } from '@/lib/stock'
import { InventoryItemCard } from './InventoryItemCard'
import type { InventoryItem, InventoryListParams } from '@/types/inventory'

export interface InventoryListProps {
  params?: InventoryListParams
  onConsume?: (id: string) => void
  onEdit?: (id: string) => void
  className?: string
}

interface StockSectionProps {
  label: string
  items: InventoryItem[]
  urgent?: boolean
  showLocation: boolean
  onConsume?: (id: string) => void
  onEdit?: (id: string) => void
}

function StockSection({ label, items, urgent = false, showLocation, onConsume, onEdit }: StockSectionProps) {
  const headingId = useId()
  const headingColor = urgent
    ? 'text-orange-700 dark:text-orange-400'
    : 'text-ui-text dark:text-ui-dark-text'
  const chipColor = urgent
    ? 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800 text-orange-700 dark:text-orange-400'
    : 'bg-ui-bg-secondary dark:bg-ui-dark-bg-secondary border-ui-border dark:border-ui-dark-border text-ui-text-secondary dark:text-ui-dark-text-secondary'

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

export function InventoryList({ params, onConsume, onEdit, className = '' }: InventoryListProps) {
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

  const { expiringSoon, groups } = buildStockView(items ?? [], {
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
      {expiringSoon.length > 0 && (
        <StockSection
          label="Expiring soon"
          items={expiringSoon}
          urgent
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
