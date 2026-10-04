'use client'

/**
 * ProductNamesList
 * The words that make a receipt line land on this product, and a way to take one back (H52).
 *
 * Before H51 a model's guess was learned as if the cook had said it: "ketchup" became a
 * key for Taco sauce, and only a merge could remove it. This is the cleanup for those keys.
 * The product's own name is listed but not removable - renaming the product changes it.
 *
 * Removal takes two taps rather than offering an undo: the general undo reverses stock
 * changes, not names, and a removed name only costs one more "auto" pre-fill.
 */

import { useState } from 'react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { fieldHintClass, fieldLabelClass } from '@/components/ui/formStyles'
import { useForgetName, useProductNames } from '@/hooks/useProducts'
import { useToast } from '@/hooks/useToast'
import { useT } from '@/lib/i18n'
import type { NameSource } from '@/types/product'

type Kind = 'name' | 'printed'

function SourceChip({ source }: { source: NameSource }) {
  const { t } = useT()
  if (source === 'canonical')
    return <Badge size="sm">{t('productSheet.names.source.canonical')}</Badge>
  if (source === 'cook')
    return (
      <Badge variant="success" size="sm">
        {t('productSheet.names.source.cook')}
      </Badge>
    )
  return (
    <Badge variant="warning" size="sm">
      {t('productSheet.names.source.auto')}
    </Badge>
  )
}

function RemoveButton({
  word,
  armed,
  busy,
  onArm,
  onConfirm,
}: {
  word: string
  armed: boolean
  busy: boolean
  onArm: () => void
  onConfirm: () => void
}) {
  const { t } = useT()
  return armed ? (
    <Button
      variant="danger"
      size="sm"
      aria-label={t('productSheet.names.confirmRemove', { word })}
      loading={busy}
      disabled={busy}
      onClick={onConfirm}
    >
      {t('productSheet.names.removeArmed')}
    </Button>
  ) : (
    <Button
      variant="ghost"
      size="sm"
      aria-label={t('productSheet.names.remove', { word })}
      onClick={onArm}
    >
      ✕
    </Button>
  )
}

export function ProductNamesList({ productId }: { productId: string }) {
  const toast = useToast()
  const { t } = useT()
  const names = useProductNames(productId)
  const forget = useForgetName(productId)
  const [armed, setArmed] = useState<string | null>(null)

  const remove = (kind: Kind, id: string, word: string) => {
    forget.mutate(
      { kind, id },
      {
        onSuccess: () => {
          setArmed(null)
          toast.success(t('productSheet.names.removed', { word }))
        },
        onError: () => toast.error(t('productSheet.names.removeError', { word })),
      }
    )
  }

  if (!names.data) return null
  const { names: learned, printed } = names.data

  return (
    <section aria-labelledby="product-names-heading" className="mt-6">
      <h3 id="product-names-heading" className={fieldLabelClass}>
        {t('productSheet.names.heading')}
      </h3>
      <p className={fieldHintClass}>
        {t('productSheet.names.hint')}
      </p>
      <ul className="mt-2 divide-y divide-ui-border dark:divide-ui-dark-border">
        {learned.map((row) => (
          <li key={row.id} className="flex items-center gap-2 py-1.5">
            <span className="flex-1">{row.name}</span>
            <SourceChip source={row.source} />
            {row.removable && (
              <RemoveButton
                word={row.name}
                armed={armed === row.id}
                busy={forget.isPending}
                onArm={() => setArmed(row.id)}
                onConfirm={() => remove('name', row.id, row.name)}
              />
            )}
          </li>
        ))}
        {printed.map((alias) => (
          <li key={alias.id} className="flex items-center gap-2 py-1.5">
            <span className="flex-1">
              <span className="font-mono text-sm">{alias.receipt_name}</span>
              <span className={`ml-2 ${fieldHintClass} inline`}>{alias.store_chain}</span>
            </span>
            {alias.verified ? (
              <Badge variant="success" size="sm">
                {t('productSheet.names.source.known')}
              </Badge>
            ) : (
              <Badge variant="warning" size="sm">
                {t('productSheet.names.source.auto')}
              </Badge>
            )}
            <RemoveButton
              word={alias.receipt_name}
              armed={armed === alias.id}
              busy={forget.isPending}
              onArm={() => setArmed(alias.id)}
              onConfirm={() => remove('printed', alias.id, alias.receipt_name)}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

export default ProductNamesList
