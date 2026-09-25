'use client'

/**
 * UndoButton (operator, 2026-09-22)
 * Always in the header, always saying what it would reverse: "Undo Finished · Apples". Pressing
 * it again steps further back. It replaces the Undo that used to live on a few toasts, which
 * vanished after eight seconds on a display nobody was necessarily watching.
 */

import React from 'react'
import Button from '@/components/ui/Button'
import { useUndo, useUndoPreview } from '@/hooks/useUndo'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import { describeUndo } from '@/lib/undo'

export function UndoButton() {
  const { data: preview } = useUndoPreview()
  const undo = useUndo()
  const toast = useToast()

  const description = preview ? describeUndo(preview) : null

  const handleUndo = () => {
    if (!preview) return
    undo.mutate(preview.batch_id, {
      onError: (error) =>
        // A 409 names what happened ("Something newer has happened since"); the refetch in
        // `onSettled` then shows the newer thing, so the next press is an informed one
        toast.error(
          isAPIError(error) && error.status < 500 && error.message
            ? error.message
            : 'Could not undo'
        ),
    })
  }

  return (
    <Button
      variant="secondary"
      size="md"
      disabled={!preview}
      loading={undo.isPending}
      aria-label={description ? `Undo ${description}` : 'Undo'}
      onClick={handleUndo}
    >
      <span aria-hidden="true">↶ Undo</span>
      {description && (
        <span
          aria-hidden="true"
          className="ml-2 max-w-[14rem] truncate text-sm font-normal text-ui-text-secondary dark:text-ui-dark-text-secondary"
        >
          {description}
        </span>
      )}
    </Button>
  )
}

export default UndoButton
