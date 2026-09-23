'use client'

/**
 * What moved under an open sheet, and the two ways out of it (H25).
 *
 * Only a field the cook has actually edited can raise one - anything else simply follows the
 * server, which is what they would want and what they would never notice.
 */

import React from 'react'
import Button from '@/components/ui/Button'
import type { FieldEdit } from '@/hooks/useFieldEdit'

export function FieldMoved({ label, field }: { label: string; field: FieldEdit }) {
  if (field.moved === null) return null
  return (
    <div
      role="status"
      className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary"
    >
      <span>{`${label} changed to ${field.moved} while this was open`}</span>
      <Button variant="ghost" size="sm" onClick={field.keepMine}>
        Keep mine
      </Button>
      <Button variant="ghost" size="sm" onClick={field.takeTheirs}>
        {`Use ${field.moved}`}
      </Button>
    </div>
  )
}

export default FieldMoved
