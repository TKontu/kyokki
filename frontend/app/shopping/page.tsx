'use client'

/**
 * The Shopping screen (frontier item 5): the backend shopping list has been complete since the
 * agent CLI started using it; this is the iPad's first view onto it. Open items grouped Urgent /
 * Normal / Low, then what has already been bought, collapsed below.
 */

import React, { useState } from 'react'
import Button from '@/components/ui/Button'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { boughtItems, GenerateSheet, groupOpenItems, QuickAddRow, ShoppingItemRow } from '@/components/shopping'
import {
  useClearPurchasedShoppingItems,
  useCreateShoppingItem,
  usePurchaseShoppingItem,
  useRemoveShoppingItem,
  useShoppingList,
} from '@/hooks/useShopping'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import type { ShoppingListItem } from '@/types/shopping'

function errorText(error: unknown, fallback: string): string {
  return isAPIError(error) && error.status < 500 && error.message ? error.message : fallback
}

export default function Shopping() {
  const { data: items, isLoading } = useShoppingList({ include_purchased: true })
  const createItem = useCreateShoppingItem()
  const purchase = usePurchaseShoppingItem()
  const removeItem = useRemoveShoppingItem()
  const clearBought = useClearPurchasedShoppingItems()
  const toast = useToast()
  const [boughtOpen, setBoughtOpen] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)

  const openGroups = groupOpenItems(items ?? [])
  const bought = boughtItems(items ?? [])

  const toggle = (item: ShoppingListItem) => {
    const next = !item.is_purchased
    purchase.mutate(
      { id: item.id, purchased: next },
      {
        onSuccess: () => {
          if (next) {
            toast.success(`Bought · ${item.name}`, {
              action: {
                label: 'Undo',
                onClick: () => purchase.mutate({ id: item.id, purchased: false }),
              },
            })
          }
        },
        onError: (error) => toast.error(errorText(error, `Could not update ${item.name}`)),
      }
    )
  }

  const remove = (item: ShoppingListItem) => {
    removeItem.mutate(item.id, {
      onError: (error) => toast.error(errorText(error, `Could not remove ${item.name}`)),
    })
  }

  const addItem: React.ComponentProps<typeof QuickAddRow>['onAdd'] = (data) => {
    createItem.mutate(data, {
      onError: (error) => toast.error(errorText(error, `Could not add ${data.name}`)),
    })
  }

  const clear = () => {
    clearBought.mutate(undefined, {
      onSuccess: (result) =>
        toast.success(`Cleared ${result.deleted_count} item${result.deleted_count === 1 ? '' : 's'}`),
      onError: (error) => toast.error(errorText(error, 'Could not clear the bought items')),
    })
  }

  return (
    <div>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Shopping</h1>
        <Button variant="secondary" size="md" onClick={() => setGenerateOpen(true)}>
          Generate from low stock
        </Button>
      </header>

      <main className="px-6 py-4">
        <div className="mb-4">
          <QuickAddRow onAdd={addItem} pending={createItem.isPending} />
        </div>

        {isLoading && <SkeletonCard />}

        {!isLoading && openGroups.length === 0 && (
          <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
            Nothing on the list.
          </p>
        )}

        {openGroups.map((group) => (
          <section key={group.key} className="mb-4">
            <h2 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
              {group.label}
            </h2>
            <ul>
              {group.items.map((item) => (
                <ShoppingItemRow
                  key={item.id}
                  item={item}
                  onToggle={() => toggle(item)}
                  onRemove={() => remove(item)}
                />
              ))}
            </ul>
          </section>
        ))}

        {bought.length > 0 && (
          <section className="mt-6 border-t border-ui-border pt-4 dark:border-ui-dark-border">
            <div className="mb-1 flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setBoughtOpen((open) => !open)}
                aria-expanded={boughtOpen}
                className="min-h-touch text-sm font-medium text-ui-text-secondary no-select dark:text-ui-dark-text-secondary"
              >
                Bought ({bought.length}) {boughtOpen ? '▾' : '▸'}
              </button>
              <Button
                variant="ghost"
                size="sm"
                loading={clearBought.isPending}
                onClick={clear}
              >
                Clear bought
              </Button>
            </div>
            {boughtOpen && (
              <ul>
                {bought.map((item) => (
                  <ShoppingItemRow
                    key={item.id}
                    item={item}
                    onToggle={() => toggle(item)}
                    onRemove={() => remove(item)}
                  />
                ))}
              </ul>
            )}
          </section>
        )}
      </main>

      <GenerateSheet open={generateOpen} onClose={() => setGenerateOpen(false)} />
    </div>
  )
}
