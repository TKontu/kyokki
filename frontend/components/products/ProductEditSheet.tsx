'use client'

/**
 * ProductEditSheet
 * Correct what the catalog believes about a product.
 *
 * A product's shelf life, piece weight and unit are learned from the first receipt
 * that created it, and until H18 none of them could be fixed afterwards. That made a
 * wrong first guess permanent: mince guessed at 5 days marks every future pack
 * expired on day six, and produce with the wrong piece weight counts wrong for ever.
 *
 * `unit_type` is derived server-side from `default_unit`, so it is never sent.
 *
 * H52 adds what the operator asked for on 2026-09-24: the category (a placeholder shelf
 * life follows it server-side), a frozen life of the product's own with the category's
 * as the fallback, and the names that make receipt lines land here.
 *
 * Q18-G2 adds the product's generated icon (ComfyUI, replacing the rejected SVG drawer): a
 * small image for a food product with no exact emoji, or the category emoji otherwise.
 * **Regenerate** queues a new render with a fresh seed, optionally with the cook's words
 * ("oval rye pastry with rice filling"), and **Use category emoji** drops the image. Neither
 * waits for Save: they act on the icon at once, and the image lands minutes later. When
 * generation is not configured on this server (`generation_enabled` false), a plain note
 * replaces the Regenerate button and its hint field. The image loads only as an <img>.
 *
 * The Q18 build adds the exact Apple emoji, ahead of the generated image in the same preview
 * (lib/productIcon.ts has the one precedence rule). A `proposed` emoji shows **Confirm** and
 * **Reject**; otherwise the picker below is limited to `GET /products/emoji/reference`, plus
 * "No emoji". None of it waits for Save either.
 *
 * Post-MVP frontier item 13 adds an editable Finnish name - a new product gets one proposed
 * in the background, marked "Proposed" until the cook edits it (`display_name_sources` says
 * whose word it is) - and, folded into this round because A1's auto-shopping sits right below
 * it, an editable Minimum stock (`min_stock_quantity`, already in the API; this sheet had no
 * field for it before).
 *
 * Icon curation (operator ask 2026-10-03) adds **Keep as canonical** - a develop-build-only
 * toggle (`ICON_CURATION_ENABLED`, `useIconLibraryStatus`) shown on an icon that is a ready,
 * actually-generated image with no emoji win, for the operator to later submit to the repo's
 * icon library (`docs/icon_library/README.md`). Folded in: **Regenerate** and its hint field
 * are now hidden whenever an exact or cook emoji wins the tile - asking for one used to reach
 * the API and fail with 409, since that image could never show; a short line explains why
 * instead.
 */

import { useState } from 'react'

import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import {
  fieldHintClass,
  fieldInputClass,
  fieldLabelClass,
} from '@/components/ui/formStyles'
import { ProductNamesList } from '@/components/products/ProductNamesList'
import { useCategories } from '@/hooks/useCategories'
import {
  useIconLibraryStatus,
  useMarkIcon,
  useUnmarkIcon,
} from '@/hooks/useIconLibrary'
import { useToast } from '@/hooks/useToast'
import {
  useClearProductIcon,
  useConfirmProductEmoji,
  useEmojiReference,
  useProduct,
  useRedrawProductIcon,
  useRejectProductEmoji,
  useSetProductEmoji,
  useUpdateProduct,
} from '@/hooks/useProducts'
import { iconUrl } from '@/lib/api/products'
import { isAPIError } from '@/lib/api/errors'
import { displayName } from '@/lib/displayName'
import { useLanguage } from '@/lib/language'
import { resolveProductIcon } from '@/lib/productIcon'
import type { Unit } from '@/types/inventory'
import { useFieldEdit } from '@/hooks/useFieldEdit'
import { FieldMoved } from '@/components/ui/FieldMoved'
import type { ProductMaster, ProductMasterUpdate } from '@/types/product'

/** An empty input is how "not known" is written in this sheet. */
function blankIfNull(value: number | null): string {
  return value == null ? '' : String(value)
}

const UNITS: Unit[] = ['pcs', 'g', 'dl', 'tsp', 'tbsp']

export interface ProductEditSheetProps {
  product: ProductMaster
  onClose: () => void
  onSaved?: (product: ProductMaster) => void
}

/** Empty means "no value"; anything else must be a positive number. */
function positiveOrNull(raw: string): number | null | undefined {
  const tidy = raw.trim()
  if (tidy === '') return null
  const value = Number(tidy)
  return Number.isFinite(value) && value > 0 ? value : undefined
}

/** Like `positiveOrNull`, but zero counts - the minimum stock threshold that turns auto
 * shopping off is zero, not "no value" (A1's sibling lane). */
function nonNegativeOrNull(raw: string): number | null | undefined {
  const tidy = raw.trim()
  if (tidy === '') return null
  const value = Number(tidy)
  return Number.isFinite(value) && value >= 0 ? value : undefined
}

export function ProductEditSheet({
  product,
  onClose,
  onSaved,
}: ProductEditSheetProps) {
  const toast = useToast()
  const [language] = useLanguage()
  const save = useUpdateProduct()
  const categories = useCategories()
  const redraw = useRedrawProductIcon()
  const clearIcon = useClearProductIcon()
  const emojiReference = useEmojiReference()
  const setEmoji = useSetProductEmoji()
  const confirmEmoji = useConfirmProductEmoji()
  const rejectEmoji = useRejectProductEmoji()
  const curationStatus = useIconLibraryStatus()
  const markIcon = useMarkIcon()
  const unmarkIcon = useUnmarkIcon()
  const [hint, setHint] = useState('')
  // What the last icon or emoji action answered, until the product itself catches up (both
  // act at once, outside Save, so this sheet's own prop is briefly behind the server).
  const [liveAnswer, setLiveAnswer] = useState<ProductMaster | null>(null)
  const [brokenIcon, setBrokenIcon] = useState<number | null>(null)
  // Polls while the icon is pending (Q18-G2, F4 review), so "Generating..." clears on its
  // own once the render lands - otherwise nothing tells this open sheet it has.
  const polled = useProduct(product.id)
  // `product` (the prop) is the baseline; an instant action's own answer (`liveAnswer`) or
  // the poll replace it once they are at least as fresh - an action that does not happen to
  // bump `updated_at` must still win over the prop it was answering (the original reason
  // for `>=`, before the poll existed), and the poll winning a tie with an *already-applied*
  // `liveAnswer` is harmless: at that point they describe the same server state.
  const liveProduct = [liveAnswer, polled.data].reduce<ProductMaster>(
    (freshest, candidate) =>
      candidate != null &&
      Date.parse(candidate.updated_at) >= Date.parse(freshest.updated_at)
        ? candidate
        : freshest,
    product
  )
  const iconVersion = liveProduct.icon_version ?? null
  const iconStatus = liveProduct.icon_status ?? null
  const generationEnabled = liveProduct.generation_enabled ?? false
  const emoji = liveProduct.emoji ?? null
  const emojiMatch = liveProduct.emoji_match ?? null
  // An exact or cook emoji already wins the tile (lib/productIcon.ts's own precedence):
  // Regenerate could never show its result, so the sheet must not offer it (the bug this
  // round folds in - it used to, and asking for one failed with 409).
  const emojiWins = emojiMatch === 'exact' || emojiMatch === 'cook'
  // Icon curation (operator ask 2026-10-03): "Keep as canonical" is offered only on a
  // develop build (curationEnabled) for an icon that is actually a ready, generated image
  // (icon_seed set - a library icon never qualifies, it is already in the library) with no
  // emoji win - the same markability the API itself enforces.
  const curationEnabled = curationStatus.data?.curation_enabled ?? false
  const iconSeed = liveProduct.icon_seed ?? null
  const markable =
    curationEnabled && iconStatus === 'ready' && iconSeed != null && !emojiWins
  const marked = liveProduct.icon_canonical_at != null

  // Each field follows the product until the cook touches it, and says so if what they are
  // editing moves underneath them (H25) - two cooks on two screens is the case this is for.
  const nameField = useFieldEdit(product.canonical_name)
  const shelfLifeField = useFieldEdit(String(product.default_shelf_life_days))
  const openedField = useFieldEdit(blankIfNull(product.opened_shelf_life_days))
  const pieceField = useFieldEdit(blankIfNull(product.avg_piece_grams))
  const packField = useFieldEdit(blankIfNull(product.pack_grams))
  const unitField = useFieldEdit(product.default_unit)
  const categoryField = useFieldEdit(product.category)
  const frozenField = useFieldEdit(blankIfNull(product.frozen_shelf_life_days))
  // Follows `liveProduct`, not the prop: a background proposal (Post-MVP frontier item 13)
  // may land while this sheet is open, the same as the icon and the emoji do.
  const displayNameField = useFieldEdit(liveProduct.display_names?.fi ?? '')
  const minStockField = useFieldEdit(blankIfNull(product.min_stock_quantity))
  const name = nameField.value
  const shelfLife = shelfLifeField.value
  const openedShelfLife = openedField.value
  const pieceGrams = pieceField.value
  const packGrams = packField.value
  const unit = unitField.value as Unit
  const category = categoryField.value
  const frozenShelfLife = frozenField.value
  const displayNameFi = displayNameField.value
  const minStock = minStockField.value

  const shelfLifeValue = positiveOrNull(shelfLife)
  const openedValue = positiveOrNull(openedShelfLife)
  const pieceValue = positiveOrNull(pieceGrams)
  const packValue = positiveOrNull(packGrams)
  const frozenValue = positiveOrNull(frozenShelfLife)
  const minStockValue = nonNegativeOrNull(minStock)

  // Shelf life is the one field that may not be blank: every expiry date comes from it.
  const valid =
    name.trim() !== '' &&
    typeof shelfLifeValue === 'number' &&
    openedValue !== undefined &&
    pieceValue !== undefined &&
    packValue !== undefined &&
    frozenValue !== undefined &&
    minStockValue !== undefined

  // Send only what changed, so two cooks editing different fields do not fight - and only
  // what *this* cook changed, so a field that moved underneath is left where the server has it.
  const changes: ProductMasterUpdate = {}
  if (nameField.changed && name.trim() !== product.canonical_name) {
    changes.canonical_name = name.trim()
  }
  if (shelfLifeField.changed && valid) {
    changes.default_shelf_life_days = shelfLifeValue as number
  }
  if (openedField.changed) changes.opened_shelf_life_days = openedValue ?? null
  if (pieceField.changed) changes.avg_piece_grams = pieceValue ?? null
  if (packField.changed) changes.pack_grams = packValue ?? null
  if (unitField.changed) changes.default_unit = unit
  if (categoryField.changed && category !== product.category) changes.category = category
  if (frozenField.changed) changes.frozen_shelf_life_days = frozenValue ?? null
  // Blank means "nothing typed yet" (Post-MVP frontier item 13 has no "clear" affordance,
  // unlike the emoji's `cleared` state) - only a non-empty edit is sent.
  if (displayNameField.changed && displayNameFi.trim() !== '') {
    changes.display_names = { fi: displayNameFi.trim() }
  }
  if (minStockField.changed) changes.min_stock_quantity = minStockValue ?? null

  const dirty = Object.keys(changes).length > 0

  const sortedCategories = [...(categories.data ?? [])].sort(
    (a, b) => a.sort_order - b.sort_order
  )
  const categoryFrozen = sortedCategories.find((c) => c.id === category)
    ?.frozen_shelf_life_days
  const categoryEmoji = sortedCategories.find((c) => c.id === product.category)?.icon ?? ''

  const actionError = (error: unknown, fallback: string) => {
    const readable = isAPIError(error) && error.status < 500 && error.message
    toast.error(readable ? error.message : fallback)
  }
  const regenerateIcon = () => {
    redraw.mutate(
      { id: product.id, hint },
      {
        onSuccess: (updated) => {
          setLiveAnswer(updated)
          setHint('')
        },
        onError: (error) => actionError(error, 'Could not ask for a new image'),
      }
    )
  }
  const useCategoryIcon = () => {
    clearIcon.mutate(product.id, {
      onSuccess: (updated) => setLiveAnswer(updated),
      onError: (error) => actionError(error, 'Could not change the icon'),
    })
  }
  // The mark/unmark routes answer a mark entry, not the full product (unlike every other
  // icon action here) - merged onto liveProduct, with a fresh `updated_at` so it wins the
  // freshest-of-three reduce above over whatever the prop or an earlier poll last had.
  const toggleCanonical = () => {
    const mutation = marked ? unmarkIcon : markIcon
    mutation.mutate(product.id, {
      onSuccess: (entry) =>
        setLiveAnswer({
          ...liveProduct,
          icon_canonical_at: entry.marked_at,
          updated_at: new Date().toISOString(),
        }),
      onError: (error) => actionError(error, 'Could not change the canonical mark'),
    })
  }
  const busyGenerating = redraw.isPending || iconStatus === 'pending'
  const iconNote = !generationEnabled
    ? 'Icon generation is not configured on this server'
    : iconStatus === 'pending'
      ? 'Generating… this takes a few minutes'
      : iconStatus === 'failed'
        ? 'Could not generate one this time. Try again, perhaps with a hint.'
        : iconStatus === 'cleared'
          ? 'Showing the category emoji'
          : iconStatus === null
            ? 'Not generated yet'
            : null

  const pickEmoji = (chosen: string | null) => {
    setEmoji.mutate(
      { id: product.id, emoji: chosen },
      {
        onSuccess: (updated) => setLiveAnswer(updated),
        onError: (error) => actionError(error, 'Could not change the emoji'),
      }
    )
  }
  const onConfirmEmoji = () => {
    confirmEmoji.mutate(product.id, {
      onSuccess: (updated) => setLiveAnswer(updated),
      onError: (error) => actionError(error, 'Could not confirm this emoji'),
    })
  }
  const onRejectEmoji = () => {
    rejectEmoji.mutate(product.id, {
      onSuccess: (updated) => setLiveAnswer(updated),
      onError: (error) => actionError(error, 'Could not reject this emoji'),
    })
  }
  const emojiNote =
    emojiMatch === 'proposed'
      ? 'A guess, waiting to be confirmed'
      : emojiMatch === 'cook'
        ? 'Your own choice'
        : emojiMatch === 'exact'
          ? 'Exact match'
          : null

  const submit = () => {
    save.mutate(
      { id: product.id, data: changes },
      {
        onSuccess: (updated) => {
          toast.success(`Saved ${updated.canonical_name}`)
          onSaved?.(updated)
          onClose()
        },
        onError: (error) => {
          const readable = isAPIError(error) && error.status < 500 && error.message
          toast.error(readable ? error.message : 'Could not save this product')
        },
      }
    )
  }

  return (
    <BottomSheet
      open
      onClose={onClose}
      title={`Edit ${displayName(product.display_names, product.canonical_name, language)}`}
      footer={
        <div className="flex gap-2">
          <Button variant="secondary" fullWidth onClick={onClose}>
            Cancel
          </Button>
          <Button
            data-primary
            fullWidth
            disabled={!dirty || !valid || save.isPending}
            loading={save.isPending}
            onClick={submit}
          >
            Save
          </Button>
        </div>
      }
    >
      <fieldset className="mb-4">
        <legend className={fieldLabelClass}>Icon</legend>
        <div className="mt-1 flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-ui border border-ui-border dark:border-ui-dark-border">
            {(() => {
              const preview = resolveProductIcon({
                emoji,
                emojiMatch,
                iconVersion: iconVersion !== brokenIcon ? iconVersion : null,
                categoryIcon: categoryEmoji,
              })
              return preview.kind === 'generated' ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={iconUrl(product.id, preview.version)}
                  alt=""
                  aria-hidden="true"
                  width={40}
                  height={40}
                  className="h-10 w-10"
                  onError={() => setBrokenIcon(preview.version)}
                />
              ) : (
                <span aria-hidden="true" className="text-3xl leading-none">
                  {preview.kind === 'none' ? '' : preview.value}
                </span>
              )
            })()}
          </div>
          {iconNote && <p className={fieldHintClass}>{iconNote}</p>}
        </div>
        {generationEnabled && !emojiWins && (
          <>
            <label htmlFor="product-icon-hint" className={`${fieldLabelClass} mt-2`}>
              Hint for the image
            </label>
            <input
              id="product-icon-hint"
              type="text"
              maxLength={200}
              placeholder="optional, e.g. oval rye pastry with rice filling"
              value={hint}
              onChange={(event) => setHint(event.target.value)}
              className={`${fieldInputClass} mt-1`}
            />
          </>
        )}
        {generationEnabled && emojiWins && (
          <p className={`${fieldHintClass} mt-2`}>
            Showing the emoji. Choose &quot;No emoji&quot; to use a generated icon.
          </p>
        )}
        <div className="mt-2 flex gap-2">
          {generationEnabled && !emojiWins && (
            <Button
              variant="secondary"
              size="sm"
              loading={busyGenerating}
              onClick={regenerateIcon}
            >
              Regenerate
            </Button>
          )}
          {iconStatus !== 'cleared' && (
            <Button
              variant="ghost"
              size="sm"
              loading={clearIcon.isPending}
              onClick={useCategoryIcon}
            >
              Use category emoji
            </Button>
          )}
        </div>
        {markable && (
          <div className="mt-2">
            <Button
              variant={marked ? 'primary' : 'secondary'}
              size="sm"
              aria-pressed={marked}
              loading={markIcon.isPending || unmarkIcon.isPending}
              onClick={toggleCanonical}
            >
              {marked ? 'Canonical ✓' : 'Keep as canonical'}
            </Button>
          </div>
        )}
      </fieldset>

      <fieldset className="mb-4">
        <legend className={fieldLabelClass}>Emoji</legend>
        {emojiMatch === 'proposed' && (
          <div className="mt-1 flex items-center gap-3">
            <span aria-hidden="true" className="text-3xl leading-none">
              {emoji}
            </span>
            <p className={fieldHintClass}>{emojiNote}</p>
            <Button
              size="sm"
              loading={confirmEmoji.isPending}
              onClick={onConfirmEmoji}
            >
              Confirm
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={rejectEmoji.isPending}
              onClick={onRejectEmoji}
            >
              Reject
            </Button>
          </div>
        )}
        {emojiMatch !== 'proposed' && emojiNote && (
          <p className={`${fieldHintClass} mt-1`}>{emojiNote}</p>
        )}
        <div
          role="group"
          aria-label="Pick an emoji"
          className="mt-2 max-h-40 overflow-y-auto rounded-ui border border-ui-border p-2 dark:border-ui-dark-border"
        >
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              title="No emoji"
              aria-label="No emoji"
              aria-pressed={emojiMatch === 'cleared'}
              disabled={setEmoji.isPending}
              onClick={() => pickEmoji(null)}
              className={`flex h-9 w-9 items-center justify-center rounded-ui border text-base ${
                emojiMatch === 'cleared'
                  ? 'border-ui-text bg-ui-text text-white dark:border-ui-dark-text dark:bg-ui-dark-text dark:text-ui-dark-bg'
                  : 'border-ui-border text-ui-text dark:border-ui-dark-border dark:text-ui-dark-text'
              }`}
            >
              ∅
            </button>
            {(emojiReference.data ?? []).map((entry) => {
              // The picker's own selection mark: a table-set exact match or the cook's
              // own pick both show as "this one is chosen" - only a pending proposal does
              // not, since it is not shown anywhere until confirmed.
              const selected =
                emoji === entry.emoji && (emojiMatch === 'exact' || emojiMatch === 'cook')
              return (
                <button
                  key={entry.emoji}
                  type="button"
                  title={entry.name}
                  aria-label={entry.name}
                  aria-pressed={selected}
                  disabled={setEmoji.isPending}
                  onClick={() => pickEmoji(entry.emoji)}
                  className={`flex h-9 w-9 items-center justify-center rounded-ui border text-xl ${
                    selected
                      ? 'border-ui-text bg-ui-text dark:border-ui-dark-text dark:bg-ui-dark-text'
                      : 'border-ui-border dark:border-ui-dark-border'
                  }`}
                >
                  {entry.emoji}
                </button>
              )
            })}
          </div>
        </div>
      </fieldset>

      <label htmlFor="product-name" className={fieldLabelClass}>
        Name
      </label>
      <input
        id="product-name"
        type="text"
        aria-label="Name"
        value={name}
        onChange={(event) => nameField.set(event.target.value)}
        className={`${fieldInputClass} mt-1`}
      />
      <FieldMoved label="Name" field={nameField} />

      <label htmlFor="product-display-name-fi" className={`${fieldLabelClass} mt-4`}>
        Finnish name
      </label>
      <input
        id="product-display-name-fi"
        type="text"
        aria-label="Finnish name"
        placeholder="e.g. Maito"
        value={displayNameFi}
        onChange={(event) => displayNameField.set(event.target.value)}
        className={`${fieldInputClass} mt-1`}
      />
      <p className={fieldHintClass}>
        {liveProduct.display_name_sources?.fi === 'model'
          ? 'Proposed by the model; shown in Suomi until you change it'
          : liveProduct.display_names?.fi
            ? 'Your own name, shown in Suomi'
            : 'Blank until proposed, or typed here; English shows the canonical name either way'}
      </p>
      <FieldMoved label="Finnish name" field={displayNameField} />

      <div className="mt-4 flex flex-wrap gap-4">
        <div className="w-32">
          <label htmlFor="product-shelf-life" className={fieldLabelClass}>
            Keeps for
          </label>
          <input
            id="product-shelf-life"
            type="number"
            inputMode="numeric"
            min="1"
            aria-label="Keeps for"
            value={shelfLife}
            onChange={(event) => shelfLifeField.set(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          <p className={fieldHintClass}>
            {product.shelf_life_source === 'category'
              ? 'days, sealed; follows the category'
              : 'days, sealed'}
          </p>
          <FieldMoved label="Keeps for" field={shelfLifeField} />
        </div>

        <div className="w-32">
          <label htmlFor="product-opened-shelf-life" className={fieldLabelClass}>
            Once opened
          </label>
          <input
            id="product-opened-shelf-life"
            type="number"
            inputMode="numeric"
            min="1"
            aria-label="Once opened"
            value={openedShelfLife}
            onChange={(event) => openedField.set(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          <p className={fieldHintClass}>days, blank if unknown</p>
          <FieldMoved label="Once opened" field={openedField} />
        </div>

        <div className="w-32">
          <label htmlFor="product-frozen-shelf-life" className={fieldLabelClass}>
            Once frozen
          </label>
          <input
            id="product-frozen-shelf-life"
            type="number"
            inputMode="numeric"
            min="1"
            aria-label="Once frozen"
            placeholder={categoryFrozen == null ? '' : String(categoryFrozen)}
            value={frozenShelfLife}
            onChange={(event) => frozenField.set(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          <p className={fieldHintClass}>days, blank for the category&apos;s</p>
          <FieldMoved label="Once frozen" field={frozenField} />
        </div>

        <div className="w-32">
          <label htmlFor="product-piece-grams" className={fieldLabelClass}>
            One piece
          </label>
          <input
            id="product-piece-grams"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            aria-label="One piece"
            value={pieceGrams}
            onChange={(event) => pieceField.set(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          <p className={fieldHintClass}>grams, blank if unknown</p>
        </div>

        <div className="w-32">
          <label htmlFor="product-pack-grams" className={fieldLabelClass}>
            One pack
          </label>
          <input
            id="product-pack-grams"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            aria-label="One pack"
            value={packGrams}
            onChange={(event) => packField.set(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          <p className={fieldHintClass}>grams, blank if unknown</p>
        </div>

        <div className="w-32">
          <label htmlFor="product-min-stock" className={fieldLabelClass}>
            Minimum stock
          </label>
          <input
            id="product-min-stock"
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            aria-label="Minimum stock"
            value={minStock}
            onChange={(event) => minStockField.set(event.target.value)}
            className={`${fieldInputClass} mt-1`}
          />
          <p className={fieldHintClass}>{`${product.default_unit}, blank for no auto shopping`}</p>
          <FieldMoved label="Minimum stock" field={minStockField} />
        </div>
      </div>

      <div className="mt-4">
        <ChoiceGroup
          label="Counted in"
          name="product-unit"
          className="grid-cols-5"
          value={unit}
          options={UNITS.map((value) => ({ value, label: value }))}
          onChange={unitField.set}
        />
      </div>

      {sortedCategories.length > 0 && (
        <div className="mt-4">
          <ChoiceGroup
            label="Category"
            name="product-category"
            className="grid-cols-2 sm:grid-cols-3"
            value={category}
            options={sortedCategories.map((c) => ({
              value: c.id,
              label: `${c.icon ?? ''} ${c.display_name}`.trim(),
            }))}
            onChange={categoryField.set}
          />
          <FieldMoved label="Category" field={categoryField} />
        </div>
      )}

      <ProductNamesList productId={product.id} />
    </BottomSheet>
  )
}

export default ProductEditSheet
