'use client'

/**
 * useFieldEdit (H25)
 *
 * One field of a sheet, while the thing it edits moves underneath it.
 *
 * Sheets used to seed their inputs at mount and diff them against the live record, which had
 * two consequences: a background change armed Save by itself, and one press then wrote the
 * mounted value back over the server's newer one - a consume from another device came back as
 * a correction. So an untouched field **follows** the record, a touched field keeps what the
 * cook typed, and a touched field whose value also moved **says so** rather than picking a
 * winner on their behalf.
 */

import { useState } from 'react'

export interface FieldEdit {
  /** What to show: the cook's value if they typed one, otherwise the record's. */
  value: string
  /** Touched, and different from what the record says now - the only thing worth sending. */
  changed: boolean
  /** What the record says now, when that is not what the cook was working from. */
  moved: string | null
  set: (next: string) => void
  keepMine: () => void
  takeTheirs: () => void
}

export function useFieldEdit(live: string): FieldEdit {
  const [typed, setTyped] = useState<string | null>(null)
  // The live value the cook last saw for this field: what they typed over, or acknowledged
  const [seen, setSeen] = useState(live)

  return {
    value: typed ?? live,
    changed: typed !== null && typed !== live,
    moved: typed !== null && live !== seen ? live : null,
    set: (next: string) => {
      setTyped(next)
      setSeen(live)
    },
    keepMine: () => setSeen(live),
    takeTheirs: () => {
      setTyped(null)
      setSeen(live)
    },
  }
}
