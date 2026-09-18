/**
 * ReceiptStatusChip (MVP-R8)
 * Where a receipt is in its life, in the words the kitchen uses rather than the status enum.
 * A receipt that has been read but not confirmed is the one that needs a person, so it is the
 * one that stands out.
 */

import React from 'react'
import Badge, { type BadgeProps } from '@/components/ui/Badge'

type Chip = { label: string; variant: BadgeProps['variant'] }

const CHIPS: Partial<Record<string, Chip>> = {
  // Rows from before MVP-R3, when uploads were not queued
  uploaded: { label: 'Not read yet', variant: 'default' },
  queued: { label: 'Waiting to be read', variant: 'info' },
  processing: { label: 'Reading', variant: 'info' },
  completed: { label: 'Waiting for review', variant: 'warning' },
  failed: { label: 'Could not read', variant: 'error' },
  confirmed: { label: 'Added to stock', variant: 'success' },
}

// `status` is a plain string on purpose: the API can add a status without a frontend release.
export function ReceiptStatusChip({ status }: { status: string }) {
  // A status this build does not know shows itself. Falling back to "Not read yet" was a lie:
  // it would say a confirmed-and-archived receipt still needs reading (H04).
  const chip = CHIPS[status] ?? { label: status, variant: 'default' as const }
  return <Badge variant={chip.variant}>{chip.label}</Badge>
}

export default ReceiptStatusChip
