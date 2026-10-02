'use client'

/**
 * "Generate from low stock" (AG6 on the iPad): a dry run shows what would be added or raised
 * before anything is written, then "Add to list" applies the same sources for real.
 */

import React, { useEffect, useRef, useState } from 'react'
import BottomSheet from '@/components/ui/BottomSheet'
import Button from '@/components/ui/Button'
import { useGenerateShoppingList } from '@/hooks/useShopping'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import type { ShoppingGenerateResponse } from '@/types/shopping'

export interface GenerateSheetProps {
  open: boolean
  onClose: () => void
}

function errorText(error: unknown, fallback: string): string {
  return isAPIError(error) && error.status < 500 && error.message ? error.message : fallback
}

function changeCount(preview: ShoppingGenerateResponse): number {
  return preview.added.length + preview.updated.length
}

function GenerateForm({ onClose }: { onClose: () => void }) {
  const generate = useGenerateShoppingList()
  const toast = useToast()
  const [preview, setPreview] = useState<ShoppingGenerateResponse | null>(null)
  const asked = useRef(false)

  useEffect(() => {
    if (asked.current) return
    asked.current = true
    generate.mutate(
      { sources: ['low_stock'], dry_run: true },
      {
        onSuccess: setPreview,
        onError: (error) => {
          toast.error(errorText(error, 'Could not check low stock'))
          onClose()
        },
      }
    )
    // Runs once, when the sheet mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const apply = () => {
    generate.mutate(
      { sources: ['low_stock'], dry_run: false },
      {
        onSuccess: (result) => {
          const count = changeCount(result)
          toast.success(count > 0 ? `Added ${count} item${count === 1 ? '' : 's'}` : 'Nothing to add')
          onClose()
        },
        onError: (error) => toast.error(errorText(error, 'Could not generate the list')),
      }
    )
  }

  const nothingToDo = preview !== null && changeCount(preview) === 0

  return (
    <BottomSheet
      open
      onClose={onClose}
      title="Generate from low stock"
      footer={
        <div className="grid grid-cols-2 gap-3">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button
            data-primary
            size="lg"
            disabled={!preview || nothingToDo}
            loading={generate.isPending}
            onClick={apply}
          >
            Add to list
          </Button>
        </div>
      }
    >
      {!preview && (
        <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
          Checking stock…
        </p>
      )}
      {preview && (
        <div className="flex flex-col gap-4">
          {nothingToDo && preview.skipped.length === 0 && (
            <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
              Nothing is short.
            </p>
          )}
          {preview.added.length > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                New
              </h3>
              <ul>
                {preview.added.map((line) => (
                  <li key={line.product_id} className="text-ui-text dark:text-ui-dark-text">
                    {line.name} · {line.need} {line.unit}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {preview.updated.length > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                Raised
              </h3>
              <ul>
                {preview.updated.map((line) => (
                  <li key={line.product_id} className="text-ui-text dark:text-ui-dark-text">
                    {line.name} · {line.need} {line.unit}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {preview.skipped.length > 0 && (
            <section>
              <h3 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
                Skipped
              </h3>
              <ul>
                {preview.skipped.map((line) => (
                  <li
                    key={line.product_id}
                    className="text-ui-text-secondary dark:text-ui-dark-text-secondary"
                  >
                    {line.name} · {line.reason}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </BottomSheet>
  )
}

/** Mount the form only while open: it starts fresh (and asks for a new dry run) every time. */
export function GenerateSheet({ open, onClose }: GenerateSheetProps) {
  return open ? <GenerateForm onClose={onClose} /> : null
}

export default GenerateSheet
