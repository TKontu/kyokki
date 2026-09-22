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
import { cardActions, formatQuantity, type ConsumptionOption } from '@/lib/consumption'
import type { InventoryItem } from '@/types/inventory'

export interface InventoryItemCardProps {
  item: InventoryItem
  productName: string
  productCategory?: string
  /** Hide the location when the surrounding section already names it. */
  showLocation?: boolean
  /** One tap, no sheet: consume `amount` of the item, in its own unit. */
  onConsume?: (id: string, amount: number) => void
  /** "…": the sheet with every other amount, and Edit. */
  onMore?: (id: string) => void
  className?: string
}

const LOCATION_LABELS: Partial<Record<string, string>> = {
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
  onMore,
  className = '',
}) => {
  const inactive = isInactive(item.status)
  const { step, finish } = onConsume ? cardActions(item) : {}
  const hasActions = step !== undefined || onMore !== undefined
  const consume = (option: ConsumptionOption) => onConsume?.(item.id, option.amount)

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
        <CardFooter className="gap-2">
          {step && (
            // The act the cook almost always means, sized to be hit without looking and
            // pressed again for a second helping
            <Button
              variant={step.key === 'done' ? 'secondary' : 'primary'}
              size="xl"
              className="flex-1"
              aria-label={
                step.key === 'done'
                  ? `Finish ${productName}`
                  : `Consume ${formatQuantity(step.amount)} ${item.unit} of ${productName}`
              }
              onClick={() => consume(step)}
            >
              {step.label}
            </Button>
          )}
          {finish && (
            <Button
              variant="secondary"
              size="md"
              aria-label={`Finish ${productName}`}
              onClick={() => consume(finish)}
            >
              {finish.label}
            </Button>
          )}
          {onMore && (
            <Button
              variant="ghost"
              size="md"
              aria-label={`More for ${productName}`}
              onClick={() => onMore(item.id)}
            >
              …
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  )
}

export default InventoryItemCard
