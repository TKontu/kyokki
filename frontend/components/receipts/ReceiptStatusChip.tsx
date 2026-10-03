'use client'

/**
 * ReceiptStatusChip (MVP-R8)
 * Where a receipt is in its life, in the words the kitchen uses rather than the status enum.
 * A receipt that has been read but not confirmed is the one that needs a person, so it is the
 * one that stands out.
 */

import React from 'react'
import Badge, { type BadgeProps } from '@/components/ui/Badge'
import { useT } from '@/lib/i18n'

type Chip = { key: string; variant: BadgeProps['variant'] }

const CHIPS: Partial<Record<string, Chip>> = {
  // Rows from before MVP-R3, when uploads were not queued
  uploaded: { key: 'receipts.statusChip.uploaded', variant: 'default' },
  queued: { key: 'receipts.statusChip.queued', variant: 'info' },
  processing: { key: 'receipts.statusChip.processing', variant: 'info' },
  completed: { key: 'receipts.statusChip.completed', variant: 'warning' },
  failed: { key: 'receipts.statusChip.failed', variant: 'error' },
  confirmed: { key: 'receipts.statusChip.confirmed', variant: 'success' },
}

// `status` is a plain string on purpose: the API can add a status without a frontend release.
export function ReceiptStatusChip({ status }: { status: string }) {
  const { t } = useT()
  // A status this build does not know shows itself. Falling back to "Not read yet" was a lie:
  // it would say a confirmed-and-archived receipt still needs reading (H04).
  const chip = CHIPS[status]
  const label = chip ? t(chip.key) : status
  return <Badge variant={chip?.variant ?? 'default'}>{label}</Badge>
}

export default ReceiptStatusChip
