'use client'

/**
 * SplitSheet (CL8 L3, `docs/PRODUCT_IDENTITY_SPEC.md`)
 * "This is not X": a wrong join made stew and rice pies one product, so editing the item that
 * came from the stew edited the pies and vice versa. This sheet moves the wrongly joined items
 * off the product, onto a new product or an existing one, and says what moved with an Undo.
 *
 * Opened from an item (with its receipt-line group looked up from `/sources`) or from a
 * product's Sources list (with that group's items). When the item's group holds more items,
 * the rest move too unless the cook says otherwise. The printed names move with them
 * (`move_keys`, always true here), so the next receipt lands on the target.
 *
 * A new name that is already a product's answers 409 `name_exists`; the sheet then offers that
 * product, and one tap moves the items there instead.
 */

import { useState } from 'react'

import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import { fieldHintClass, fieldInputClass, fieldLabelClass } from '@/components/ui/formStyles'
import { ProductSearch } from '@/components/products/ProductSearch'
import { useCategories } from '@/hooks/useCategories'
import { useSplitProduct, useUndoReassignment } from '@/hooks/useProductSplit'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { displayName } from '@/lib/displayName'
import { useT } from '@/lib/i18n'
import { useLanguage } from '@/lib/language'
import { storeName } from '@/lib/receipts'
import type {
  NameExistsDetail,
  ProductMaster,
  ProductSource,
  ProductSplitResponse,
  ProductSplitTarget,
} from '@/types/product'

type TargetMode = 'new' | 'existing'

export interface SplitSheetProps {
  productId: string
  /** The source product's name as the cook reads it (`displayName`). */
  productName: string
  /** The source product's category: a new product starts in it. */
  productCategory?: string
  /** The items the cook chose to move. */
  itemIds: string[]
  /** Their group from `/sources`; its other items are offered too. */
  sourceGroup?: ProductSource | null
  /** Cancel: back to wherever the sheet was opened from. */
  onClose: () => void
  /** After a split. Defaults to `onClose`. */
  onDone?: () => void
}

function errorText(error: unknown, fallback: string): string {
  // 4xx messages come from the API and are meant for people; server and network failures are not
  return isAPIError(error) && error.status < 500 && error.message ? error.message : fallback
}

function nameExists(error: unknown): NameExistsDetail | null {
  if (!isAPIError(error) || error.status !== 409 || error.code !== 'name_exists') return null
  const detail = (error.details ?? {}) as Partial<NameExistsDetail>
  return typeof detail.product_id === 'string' && typeof detail.name === 'string'
    ? { code: 'name_exists', product_id: detail.product_id, name: detail.name }
    : null
}

export function SplitSheet({
  productId,
  productName,
  productCategory,
  itemIds,
  sourceGroup,
  onClose,
  onDone = onClose,
}: SplitSheetProps) {
  const toast = useToast()
  const [language] = useLanguage()
  const { t } = useT()
  const categories = useCategories()
  const split = useSplitProduct()
  const undo = useUndoReassignment()

  const [mode, setMode] = useState<TargetMode>('new')
  const [newName, setNewName] = useState('')
  const [category, setCategory] = useState(productCategory ?? '')
  const [term, setTerm] = useState('')
  const [picked, setPicked] = useState<{ id: string; name: string } | null>(null)
  const [pickedSelf, setPickedSelf] = useState(false)
  const [includeGroup, setIncludeGroup] = useState(true)
  const [conflict, setConflict] = useState<NameExistsDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const sortedCategories = [...(categories.data ?? [])].sort(
    (a, b) => a.sort_order - b.sort_order
  )
  const effectiveCategory = category || sortedCategories[0]?.id || ''

  const others = (sourceGroup?.item_ids ?? []).filter((id) => !itemIds.includes(id))
  const ids = includeGroup ? [...itemIds, ...others] : itemIds

  const groupToggleText = (() => {
    if (!sourceGroup || others.length === 0) return null
    const count = others.length
    if (sourceGroup.kind === 'manual' || !sourceGroup.label) {
      return t('split.alsoMoveManual', { count })
    }
    return sourceGroup.store_chain
      ? t('split.alsoMoveGroup', {
          count,
          label: sourceGroup.label,
          chain: storeName({ store_chain: sourceGroup.store_chain }, language),
        })
      : t('split.alsoMoveGroupNoChain', { count, label: sourceGroup.label })
  })()

  // The printed name follows the items (`move_keys`), so say where the next receipt goes
  const printedLabel = sourceGroup?.kind === 'receipt' ? sourceGroup.label : ''
  const keysNote = !printedLabel
    ? null
    : mode === 'new'
      ? t('split.keysNoteNew', { label: printedLabel })
      : picked
        ? t('split.keysNoteExisting', { label: printedLabel, name: picked.name })
        : null

  const productLabel = (product: ProductMaster) =>
    displayName(product.display_names, product.canonical_name, language)

  const undoSplit = (result: ProductSplitResponse) => {
    undo
      .mutateAsync(result.reassignment_id)
      .then((restored) =>
        toast.success(
          t('split.undoneToast', { count: restored.restored_item_ids.length, name: productName })
        )
      )
      .catch((undoError: unknown) =>
        toast.error(
          isAPIError(undoError) && undoError.status === 409
            ? t('split.undoStale')
            : t('split.undoError')
        )
      )
  }

  const succeeded = (result: ProductSplitResponse) => {
    onDone()
    toast.success(
      t('split.movedToast', {
        count: result.moved_item_ids.length,
        name: productLabel(result.target_product),
      }),
      {
        // Long enough to read what moved and still reach Undo
        duration: 8000,
        action: { label: t('split.undo'), onClick: () => undoSplit(result) },
      }
    )
    // The cook's own number stays on the source with nothing left to learn from: say so,
    // since it was probably set for the items that just moved away
    const shelfLife = result.source_shelf_life
    if (shelfLife && shelfLife.source === 'cook' && shelfLife.observations_left === 0) {
      toast.success(
        t('split.shelfLifeNote', {
          name: productLabel(result.source_product),
          count: shelfLife.days,
        }),
        { duration: 8000 }
      )
    }
  }

  const submit = (target: ProductSplitTarget) => {
    setError(null)
    setConflict(null)
    split.mutate(
      { productId, body: { item_ids: ids, target, move_keys: true } },
      {
        onSuccess: succeeded,
        onError: (failure) => {
          const existing = nameExists(failure)
          if (existing) setConflict(existing)
          else setError(errorText(failure, t('split.error')))
        },
      }
    )
  }

  const move = () => {
    if (mode === 'new') {
      submit({ new: { name: newName.trim(), category: effectiveCategory } })
    } else if (picked) {
      submit({ product_id: picked.id })
    }
  }

  const moveToExisting = (existing: NameExistsDetail) => {
    setMode('existing')
    setPicked({ id: existing.product_id, name: existing.name })
    setPickedSelf(false)
    submit({ product_id: existing.product_id })
  }

  const pickExisting = (product: ProductMaster) => {
    // ProductSearch lists every match, the source included: moving onto itself is no move
    if (product.id === productId) {
      setPicked(null)
      setPickedSelf(true)
      return
    }
    setPickedSelf(false)
    setPicked({ id: product.id, name: productLabel(product) })
  }

  const ready =
    ids.length > 0 &&
    (mode === 'new' ? newName.trim() !== '' && effectiveCategory !== '' : picked !== null)

  return (
    <BottomSheet
      open
      onClose={onClose}
      title={t('split.title', { name: productName })}
      footer={
        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t('split.cancel')}
          </Button>
          <Button
            data-primary
            size="lg"
            disabled={!ready || split.isPending}
            loading={split.isPending}
            onClick={move}
          >
            {t('split.move')}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-base text-ui-text dark:text-ui-dark-text">
          {t('split.intro', { count: ids.length, name: productName })}
        </p>

        {groupToggleText && (
          <label className="flex min-h-touch cursor-pointer items-center gap-3 text-base text-ui-text dark:text-ui-dark-text">
            <input
              type="checkbox"
              className="h-6 w-6 shrink-0"
              checked={includeGroup}
              onChange={(event) => setIncludeGroup(event.target.checked)}
            />
            <span>{groupToggleText}</span>
          </label>
        )}

        <ChoiceGroup<TargetMode>
          label={t('split.targetLabel')}
          name="split-target"
          className="grid-cols-2"
          value={mode}
          options={[
            { value: 'new', label: t('split.newProduct') },
            { value: 'existing', label: t('split.existingProduct') },
          ]}
          onChange={(next) => {
            setMode(next)
            setConflict(null)
            setError(null)
          }}
        />

        {mode === 'new' && (
          <>
            <div>
              <label htmlFor="split-new-name" className={fieldLabelClass}>
                {t('split.nameLabel')}
              </label>
              <input
                id="split-new-name"
                type="text"
                autoComplete="off"
                placeholder={t('split.namePlaceholder')}
                value={newName}
                onChange={(event) => {
                  setNewName(event.target.value)
                  setConflict(null)
                }}
                className={`${fieldInputClass} mt-1`}
              />
            </div>
            <div>
              <label htmlFor="split-category" className={fieldLabelClass}>
                {t('split.category')}
              </label>
              <select
                id="split-category"
                value={effectiveCategory}
                onChange={(event) => setCategory(event.target.value)}
                className={`${fieldInputClass} mt-1 min-h-touch`}
              >
                {sortedCategories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {`${c.icon ?? ''} ${c.display_name}`.trim()}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {mode === 'existing' &&
          (picked ? (
            <div className="flex items-center justify-between gap-3">
              <p className="text-base text-ui-text dark:text-ui-dark-text">
                {t('split.pickedTarget', { name: picked.name })}
              </p>
              <Button variant="secondary" size="md" onClick={() => setPicked(null)}>
                {t('split.changeTarget')}
              </Button>
            </div>
          ) : (
            <div>
              <ProductSearch
                categories={categories.data ?? []}
                term={term}
                onTermChange={(next) => {
                  setTerm(next)
                  setPickedSelf(false)
                }}
                onPickExisting={pickExisting}
                onPickNew={(name) => {
                  setMode('new')
                  setNewName(name)
                }}
                inputId="split-product-search"
              />
              {pickedSelf && (
                <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
                  {t('split.sameProduct', { name: productName })}
                </p>
              )}
            </div>
          ))}

        {keysNote && <p className={fieldHintClass}>{keysNote}</p>}

        {conflict && (
          <div role="alert" className="flex flex-col gap-2">
            <p className="text-base text-ui-text dark:text-ui-dark-text">
              {t('split.nameExists', { name: conflict.name })}
            </p>
            <Button
              variant="secondary"
              size="lg"
              loading={split.isPending}
              onClick={() => moveToExisting(conflict)}
            >
              {t('split.moveToExisting', { name: conflict.name })}
            </Button>
          </div>
        )}

        {error && (
          <p role="alert" className="text-base text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
      </div>
    </BottomSheet>
  )
}

export default SplitSheet
