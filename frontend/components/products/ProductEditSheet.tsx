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
 */

import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { ChoiceGroup } from '@/components/ui/ChoiceGroup'
import {
  fieldHintClass,
  fieldInputClass,
  fieldLabelClass,
} from '@/components/ui/formStyles'
import { useToast } from '@/hooks/useToast'
import { useUpdateProduct } from '@/hooks/useProducts'
import { isAPIError } from '@/lib/api/errors'
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

export function ProductEditSheet({
  product,
  onClose,
  onSaved,
}: ProductEditSheetProps) {
  const toast = useToast()
  const save = useUpdateProduct()

  // Each field follows the product until the cook touches it, and says so if what they are
  // editing moves underneath them (H25) - two cooks on two screens is the case this is for.
  const nameField = useFieldEdit(product.canonical_name)
  const shelfLifeField = useFieldEdit(String(product.default_shelf_life_days))
  const openedField = useFieldEdit(blankIfNull(product.opened_shelf_life_days))
  const pieceField = useFieldEdit(blankIfNull(product.avg_piece_grams))
  const packField = useFieldEdit(blankIfNull(product.pack_grams))
  const unitField = useFieldEdit(product.default_unit)
  const name = nameField.value
  const shelfLife = shelfLifeField.value
  const openedShelfLife = openedField.value
  const pieceGrams = pieceField.value
  const packGrams = packField.value
  const unit = unitField.value as Unit

  const shelfLifeValue = positiveOrNull(shelfLife)
  const openedValue = positiveOrNull(openedShelfLife)
  const pieceValue = positiveOrNull(pieceGrams)
  const packValue = positiveOrNull(packGrams)

  // Shelf life is the one field that may not be blank: every expiry date comes from it.
  const valid =
    name.trim() !== '' &&
    typeof shelfLifeValue === 'number' &&
    openedValue !== undefined &&
    pieceValue !== undefined &&
    packValue !== undefined

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

  const dirty = Object.keys(changes).length > 0

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
      title={`Edit ${product.canonical_name}`}
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
          <p className={fieldHintClass}>days, sealed</p>
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
    </BottomSheet>
  )
}

export default ProductEditSheet
