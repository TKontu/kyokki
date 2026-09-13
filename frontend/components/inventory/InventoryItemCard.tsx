import React from 'react'
import Card, {
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { ExpiryBadge } from './ExpiryBadge'
import { QuantityBar } from './QuantityBar'
import type { InventoryItem, InventoryLocation } from '@/types/inventory'

export interface InventoryItemCardProps {
  item: InventoryItem
  productName: string
  productCategory?: string
  /** Hide the location when the surrounding section already names it. */
  showLocation?: boolean
  onConsume?: (id: string) => void
  onEdit?: (id: string) => void
  className?: string
}

const LOCATION_LABELS: Record<InventoryLocation, string> = {
  main_fridge: 'Main Fridge',
  freezer: 'Freezer',
  pantry: 'Pantry',
}

const isInactive = (status: InventoryItem['status']) =>
  status === 'empty' || status === 'discarded'

export const InventoryItemCard: React.FC<InventoryItemCardProps> = ({
  item,
  productName,
  productCategory,
  showLocation = true,
  onConsume,
  onEdit,
  className = '',
}) => {
  const inactive = isInactive(item.status)
  const hasActions = onConsume !== undefined || onEdit !== undefined

  // Unknown locations (the API accepts any string) show their raw value rather than vanish
  const locationLabel = showLocation
    ? LOCATION_LABELS[item.location] ?? item.location
    : undefined

  const subtitle = [
    productCategory,
    locationLabel,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <Card
      className={`${inactive ? 'opacity-60' : ''} ${className}`.trim()}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{productName}</CardTitle>
          {subtitle && (
            <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
        <StatusBadge status={item.status} />
      </CardHeader>

      <CardContent className="flex flex-col gap-3">
        <ExpiryBadge
          expiryDate={item.expiry_date}
          expirySource={item.expiry_source}
        />
        <QuantityBar
          current={item.current_quantity}
          initial={item.initial_quantity}
          unit={item.unit}
        />
      </CardContent>

      {hasActions && (
        <CardFooter className="justify-end">
          {onConsume && (
            <Button
              variant="primary"
              size="md"
              disabled={inactive}
              onClick={() => onConsume(item.id)}
            >
              Consume
            </Button>
          )}
          {onEdit && (
            <Button
              variant="ghost"
              size="md"
              onClick={() => onEdit(item.id)}
            >
              Edit
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  )
}

export default InventoryItemCard
