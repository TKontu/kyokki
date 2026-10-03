'use client'

/**
 * The Shopping screen (frontier item 5): the backend shopping list has been complete since the
 * agent CLI started using it; this is the iPad's first view onto it. Open items grouped Urgent /
 * Normal / Low, then what has already been bought, collapsed below.
 */

import React, { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import Button from '@/components/ui/Button'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { boughtItems, GenerateSheet, groupOpenItems, QuickAddRow, ShoppingItemRow } from '@/components/shopping'
import {
  shoppingKeys,
  useClearPurchasedShoppingItems,
  useCreateShoppingItem,
  usePurchaseShoppingItem,
  useRemoveShoppingItem,
  useShoppingList,
} from '@/hooks/useShopping'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { newIdempotencyKey } from '@/lib/api/shopping'
import { useT } from '@/lib/i18n'
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
  const queryClient = useQueryClient()
  const { t } = useT()
  const [boughtOpen, setBoughtOpen] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)

  const openGroups = groupOpenItems(items ?? [])
  const bought = boughtItems(items ?? [])

  /**
   * One tick, undo or retry of either is a single user action (F1): `idempotencyKey` is minted
   * once - by `toggle` for a tick, or by the "Undo" toast's own `onClick` for an undo - and
   * `retry` (the error toast's own action) reuses that same key rather than minting a new one.
   */
  const purchaseItem = (item: ShoppingListItem, purchased: boolean, idempotencyKey: string) => {
    const retry = () => purchaseItem(item, purchased, idempotencyKey)
    purchase.mutate(
      { id: item.id, purchased, idempotencyKey },
      {
        onSuccess: () => {
          if (purchased) {
            toast.success(t('shopping.boughtToast', { name: item.name }), {
              action: {
                label: t('shopping.undo'),
                onClick: () => purchaseItem(item, false, newIdempotencyKey()),
              },
            })
          }
        },
        onError: (error) => {
          if (!purchased) {
            // F2: an undo (including a plain un-tick) used to have no onError, so a failure
            // was silent and the item stayed bought. F3 cancelled the in-flight list fetch for
            // this mutation, so refetch explicitly rather than leave a possibly stale cache.
            toast.error(t('shopping.undoFailedToast'), {
              action: { label: t('shopping.retry'), onClick: retry },
            })
            queryClient.invalidateQueries({ queryKey: shoppingKeys.all })
          } else {
            toast.error(errorText(error, t('shopping.updateError', { name: item.name })), {
              action: { label: t('shopping.retry'), onClick: retry },
            })
          }
        },
      }
    )
  }

  const toggle = (item: ShoppingListItem) =>
    purchaseItem(item, !item.is_purchased, newIdempotencyKey())

  // F1: the same per-action idempotency key the purchase action already mints - one here,
  // once per remove, rather than the bare id `useRemoveShoppingItem` otherwise mints a fresh
  // key for on every call, including a would-be retry of the same remove.
  const remove = (item: ShoppingListItem) => {
    const idempotencyKey = newIdempotencyKey()
    removeItem.mutate(
      { id: item.id, idempotencyKey },
      {
        onError: (error) => toast.error(errorText(error, t('shopping.removeError', { name: item.name }))),
      }
    )
  }

  const addItem: React.ComponentProps<typeof QuickAddRow>['onAdd'] = (data, idempotencyKey) =>
    createItem.mutateAsync({ data, idempotencyKey }).catch((error: unknown) => {
      toast.error(errorText(error, t('shopping.addError', { name: data.name })))
      throw error
    })

  const clear = () => {
    clearBought.mutate(undefined, {
      onSuccess: (result) =>
        toast.success(t('shopping.clearedToast', { count: result.deleted_count })),
      onError: (error) => toast.error(errorText(error, t('shopping.clearError'))),
    })
  }

  return (
    <div>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">
          {t('shopping.header.title')}
        </h1>
        <Button variant="secondary" size="md" onClick={() => setGenerateOpen(true)}>
          {t('shopping.header.generate')}
        </Button>
      </header>

      <main className="px-6 py-4">
        <div className="mb-4">
          <QuickAddRow onAdd={addItem} pending={createItem.isPending} />
        </div>

        {isLoading && <SkeletonCard />}

        {!isLoading && openGroups.length === 0 && (
          <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
            {t('shopping.empty')}
          </p>
        )}

        {openGroups.map((group) => (
          <section key={group.key} className="mb-4">
            <h2 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
              {t(`shopping.groups.${group.key}`)}
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
                {t('shopping.bought', { count: bought.length })} {boughtOpen ? '▾' : '▸'}
              </button>
              <Button
                variant="ghost"
                size="sm"
                loading={clearBought.isPending}
                onClick={clear}
              >
                {t('shopping.clearBought')}
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
