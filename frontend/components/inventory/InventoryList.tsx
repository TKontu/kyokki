import React from 'react'
import { useInventoryList } from '@/hooks/useInventory'
import { InventoryItemCard } from './InventoryItemCard'
import type { InventoryListParams } from '@/types/inventory'

export interface InventoryListProps {
  params?: InventoryListParams
  productNames?: Record<string, string>
  onConsume?: (id: string) => void
  onEdit?: (id: string) => void
  className?: string
}

function resolveProductName(
  productMasterId: string,
  productNames?: Record<string, string>
): string {
  return productNames?.[productMasterId] ?? `Product ${productMasterId.slice(0, 8)}`
}

export function InventoryList({
  params,
  productNames,
  onConsume,
  onEdit,
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
      <p role="alert" className="text-sm text-red-600 dark:text-red-400 py-4">
        {error instanceof Error ? error.message : 'Failed to load inventory.'}
      </p>
    )
  }

  if (!items?.length) {
    return (
      <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary py-4">
        No items found. Scan a product to add it to your inventory.
      </p>
    )
  }

  return (
    <ul className={`space-y-3 ${className}`.trim()}>
      {items.map((item) => (
        <li key={item.id}>
          <InventoryItemCard
            item={item}
            productName={resolveProductName(item.product_master_id, productNames)}
            onConsume={onConsume}
            onEdit={onEdit}
          />
        </li>
      ))}
    </ul>
  )
}

export default InventoryList
