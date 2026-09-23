'use client'

/**
 * ProductSearch
 * Find an existing product by name, or say it is a new one.
 *
 * Extracted from QuickAddSheet so the receipt review row can offer the same control
 * (H15). Interactive search is one of the two places string similarity still belongs:
 * a person makes the final choice, so a near miss costs a glance rather than a wrong
 * product learned for ever.
 */

import { useMemo } from 'react'
import {
  fieldInputClass,
  fieldLabelClass,
} from '@/components/ui/formStyles'
import { useProductSearch } from '@/hooks/useProducts'
import type { Category } from '@/types/category'
import type { ProductMaster } from '@/types/product'

export interface ProductSearchProps {
  categories: Category[]
  onPickExisting: (product: ProductMaster) => void
  /** Called with the typed name when the cook says this is a new product. */
  onPickNew: (name: string) => void
  /**
   * Controlled by the caller so the term survives the caller's own navigation -
   * QuickAddSheet's Back button returns to a search box that still has the text in it.
   */
  term: string
  onTermChange: (term: string) => void
  /** Label for the "new product" entry; defaults to the Quick Add wording. */
  newLabel?: (term: string) => string
  inputId?: string
  placeholder?: string
}

export function ProductSearch({
  categories,
  onPickExisting,
  onPickNew,
  term,
  onTermChange,
  newLabel = (term) => `Create new: ${term}`,
  inputId = 'product-search',
  placeholder = 'Milk, ground beef, apples…',
}: ProductSearchProps) {
  const search = useProductSearch(term)

  const categoryById = useMemo(
    () => new Map(categories.map((category) => [category.id, category])),
    [categories]
  )

  const trimmed = term.trim()
  const results = trimmed && search.settled ? (search.data ?? []) : []
  // Offering "new" for a name that already exists is how duplicates got made - and so is
  // offering it before the search for *this* word has answered, when nothing can be known yet
  // (H25).
  const exactMatch = results.some(
    (product) => product.canonical_name.toLowerCase() === trimmed.toLowerCase()
  )
  const offerNew = Boolean(trimmed) && search.settled && !exactMatch

  return (
    <>
      <label htmlFor={inputId} className={fieldLabelClass}>
        Product
      </label>
      <input
        id={inputId}
        type="search"
        autoComplete="off"
        value={term}
        onChange={(event) => onTermChange(event.target.value)}
        placeholder={placeholder}
        className={`${fieldInputClass} mt-1`}
      />
      <ul className="mt-3 flex flex-col gap-2">
        {results.map((product) => (
          <li key={product.id}>
            <button
              type="button"
              aria-label={product.canonical_name}
              onClick={() => onPickExisting(product)}
              className="flex w-full min-h-touch items-center gap-2 rounded-ui border border-ui-border dark:border-ui-dark-border px-3 text-left text-ui-text dark:text-ui-dark-text"
            >
              <span aria-hidden="true">
                {categoryById.get(product.category)?.icon ?? ''}
              </span>
              {product.canonical_name}
            </button>
          </li>
        ))}
        {offerNew && (
          <li>
            <button
              type="button"
              onClick={() => onPickNew(trimmed)}
              className="flex w-full min-h-touch items-center rounded-ui border border-dashed border-ui-border dark:border-ui-dark-border px-3 text-left text-ui-text dark:text-ui-dark-text"
            >
              {newLabel(trimmed)}
            </button>
          </li>
        )}
      </ul>
    </>
  )
}

export default ProductSearch
