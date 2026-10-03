'use client'

/**
 * ProvenanceChip
 * Whether a proposed product is something the kitchen already knows, or a guess.
 *
 * The row used to print `match_confidence` next to the product name - and because the
 * pipeline only kept matches at or above a score of 80, every guess read "high",
 * including the ones that paired Pineapple with Apple. This says the one thing that
 * actually matters to the cook: has this mapping been confirmed before, or is it being
 * proposed right now?
 */

import Badge from '@/components/ui/Badge'
import { useT } from '@/lib/i18n'
import type { MatchSource } from '@/types/receipt'

export interface ProvenanceChipProps {
  source: MatchSource | null
  verified: boolean
}

export function ProvenanceChip({ source, verified }: ProvenanceChipProps) {
  const { t } = useT()
  if (!source || source === 'none') return null

  return verified ? (
    <Badge variant="success" size="sm">
      {t('receipt.provenance.known')}
    </Badge>
  ) : (
    <Badge variant="warning" size="sm">
      {t('receipt.provenance.auto')}
    </Badge>
  )
}

export default ProvenanceChip
