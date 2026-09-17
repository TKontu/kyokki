/**
 * ReceiptStatusChip (MVP-R8)
 * Where a receipt is in its life, in the words the kitchen uses rather than the status enum.
 * A receipt that has been read but not confirmed is the one that needs a person, so it is the
 * one that stands out.
 */

import React from 'react'
import Badge, { type BadgeProps } from '@/components/ui/Badge'
import type { ReceiptStatus } from '@/types/receipt'

type Chip = { label: string; variant: BadgeProps['variant'] }

const CHIPS: Record<ReceiptStatus, Chip> = {
  // Rows from before MVP-R3, when uploads were not queued
  uploaded: { label: 'Not read yet', variant: 'default' },
  queued: { label: 'Waiting to be read', variant: 'info' },
  processing: { label: 'Reading', variant: 'info' },
  completed: { label: 'Waiting for review', variant: 'warning' },
  failed: { label: 'Could not read', variant: 'error' },
  confirmed: { label: 'Added to stock', variant: 'success' },
}

export function ReceiptStatusChip({ status }: { status: ReceiptStatus }) {
  const chip = CHIPS[status] ?? CHIPS.uploaded
  return <Badge variant={chip.variant}>{chip.label}</Badge>
}

export default ReceiptStatusChip
