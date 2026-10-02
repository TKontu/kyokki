'use client'

/**
 * Gone (operator trial, 2026-09-22).
 *
 * Every discard has written a waste row since MVP-S1 and nothing ever read one back: the
 * number the app exists to reduce was invisible. This is that list - thrown away and finished,
 * newest first - and the only screen that shows items no longer in stock, so it is also the
 * way back from *Mark as gone* once the header's Undo has moved on.
 *
 * The window is the screen's, not the data's: the history is kept for good, because metrics
 * will be built on it.
 */

import React, { useState } from 'react'
import Button from '@/components/ui/Button'
import { SkeletonCard } from '@/components/ui/Skeleton'
import {
  useConsumptionLog,
  useConsumptionSummary,
  useWasteStats,
  useWasteTrend,
} from '@/hooks/useConsumptionLog'
import { useUpdateInventoryItem } from '@/hooks/useInventory'
import { useToast } from '@/hooks/useToast'
import { isAPIError } from '@/lib/api/errors'
import {
  GONE_ACTIONS,
  groupByDay,
  sinceFor,
  summaryLine,
  topWastingCategories,
  wasteRateLine,
  weekLabel,
  WINDOWS,
} from '@/lib/gone'
import type { ConsumptionLogEntry, WasteStats, WasteTrend } from '@/types/consumption'

const PAGE_SIZE = 50

/** The headline rate, and the categories that waste the most (planner ruling, 2026-10-02). */
function WasteRateCard({ stats }: { stats: WasteStats | undefined }) {
  const headline = wasteRateLine(stats)
  const categories = stats ? topWastingCategories(stats.categories) : []

  return (
    <section
      aria-label="Waste rate"
      className="mb-4 rounded-ui border border-ui-border bg-ui-bg-secondary p-4 dark:border-ui-dark-border dark:bg-ui-dark-bg-secondary"
    >
      {headline ? (
        <p className="text-lg font-semibold text-ui-text dark:text-ui-dark-text">{headline}</p>
      ) : (
        <p className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
          Not enough has gone in this window to show a rate yet.
        </p>
      )}

      {categories.length > 0 && (
        <ul className="mt-3 space-y-1">
          {categories.map((category) => (
            <li
              key={category.category}
              className="flex items-center justify-between gap-4 text-sm"
            >
              <span className="text-ui-text-secondary dark:text-ui-dark-text-secondary">
                {category.display_name}
              </span>
              <span className="font-medium text-ui-text dark:text-ui-dark-text">
                {Math.round(category.rate * 100)} %
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** A compact 8-bar week trend, plain divs - no chart dependency. */
function WasteTrendChart({ trend }: { trend: WasteTrend | undefined }) {
  const weeks = trend?.weeks ?? []
  if (weeks.length === 0) return null

  return (
    <section aria-label="Waste rate, last 8 weeks" className="mb-6">
      <h2 className="mb-2 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
        Last 8 weeks
      </h2>
      <div className="flex items-end gap-2">
        {weeks.map((week) => {
          const percent = week.rate === null ? 0 : Math.round(week.rate * 100)
          const title =
            week.total === 0
              ? `${weekLabel(week)}: nothing gone`
              : `${weekLabel(week)}: ${week.discarded} of ${week.total} (${percent} %)`
          return (
            <div key={week.week_start} className="flex flex-1 flex-col items-center gap-1">
              <div
                className="flex h-20 w-full items-end overflow-hidden rounded-ui-sm bg-ui-bg-tertiary dark:bg-ui-dark-bg-tertiary"
                title={title}
              >
                <div
                  aria-hidden="true"
                  className="w-full rounded-ui-sm bg-error/70 dark:bg-error/60"
                  style={{ height: `${percent}%` }}
                />
              </div>
              <span className="text-xs text-ui-text-tertiary dark:text-ui-dark-text-tertiary">
                {weekLabel(week)}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function Row({ row, onRestore }: { row: ConsumptionLogEntry; onRestore: () => void }) {
  const thrownAway = row.action === 'discard'
  return (
    <li className="flex items-center gap-3 border-b border-ui-border py-3 last:border-b-0 dark:border-ui-dark-border">
      <span aria-hidden="true" className="text-xl leading-none">
        {thrownAway ? '🗑' : '✓'}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ui-text dark:text-ui-dark-text">
          {row.product_name}
        </p>
        <p className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
          {thrownAway ? 'Thrown away' : 'Finished'}
        </p>
      </div>
      {/* Only what is still in the bin can come back. Something finished is simply eaten, and
          an item that has since been deleted leaves its record without anything to restore. */}
      {row.item_status === 'discarded' && row.inventory_item_id && (
        <Button
          variant="secondary"
          size="md"
          aria-label={`Put ${row.product_name} back`}
          onClick={onRestore}
        >
          Put it back
        </Button>
      )}
    </li>
  )
}

export default function Gone() {
  const [windowDays, setWindowDays] = useState<number | null>(
    WINDOWS.find((each) => each.default)?.days ?? 30
  )
  const [limit, setLimit] = useState(PAGE_SIZE)
  const since = sinceFor(windowDays)
  const toast = useToast()
  const restore = useUpdateInventoryItem()

  const { data: rows, isLoading } = useConsumptionLog({
    action: GONE_ACTIONS,
    since,
    limit,
  })
  const { data: summary } = useConsumptionSummary({ since })
  const { data: wasteStats } = useWasteStats({ since })
  const { data: wasteTrend } = useWasteTrend()

  const putBack = (row: ConsumptionLogEntry) => {
    if (!row.inventory_item_id) return
    // The status sent is only a signal: the server classifies the event from it and derives
    // the result - `opened`, or `empty` when nothing was left. Never `sealed`; it was in the
    // bin (H23). The update hook invalidates stock, the history and the undo preview.
    restore.mutate(
      { id: row.inventory_item_id, data: { status: 'opened' } },
      {
        onSuccess: () => toast.success(`Back in the kitchen · ${row.product_name}`),
        onError: (error) =>
          toast.error(
            isAPIError(error) && error.status < 500 && error.message
              ? error.message
              : `Could not put ${row.product_name} back`
          ),
      }
    )
  }

  const groups = groupByDay(rows ?? [])

  return (
    <div>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-ui-border px-6 py-4 dark:border-ui-dark-border">
        <h1 className="text-xl font-semibold text-ui-text dark:text-ui-dark-text">Gone</h1>
        <div className="flex gap-2" role="group" aria-label="How far back">
          {WINDOWS.map((each) => (
            <Button
              key={each.label}
              size="md"
              variant={each.days === windowDays ? 'primary' : 'ghost'}
              aria-pressed={each.days === windowDays}
              onClick={() => {
                setWindowDays(each.days)
                setLimit(PAGE_SIZE)
              }}
            >
              {each.label}
            </Button>
          ))}
        </div>
      </header>

      <main className="px-6 py-4">
        <dl className="mb-4 flex flex-wrap gap-x-8 gap-y-2">
          <div>
            <dt className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
              Thrown away
            </dt>
            <dd className="text-lg font-semibold text-ui-text dark:text-ui-dark-text">
              {summaryLine(summary?.discard)}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-ui-text-secondary dark:text-ui-dark-text-secondary">
              Finished
            </dt>
            <dd className="text-lg font-semibold text-ui-text dark:text-ui-dark-text">
              {summaryLine(summary?.use_full)}
            </dd>
          </div>
        </dl>

        <WasteRateCard stats={wasteStats} />
        <WasteTrendChart trend={wasteTrend} />

        {isLoading && <SkeletonCard />}

        {!isLoading && groups.length === 0 && (
          <p className="py-8 text-center text-ui-text-secondary dark:text-ui-dark-text-secondary">
            Nothing has been thrown away or finished in this window.
          </p>
        )}

        {groups.map((group) => (
          <section key={group.label} className="mb-4">
            <h2 className="mb-1 text-sm font-medium text-ui-text-secondary dark:text-ui-dark-text-secondary">
              {group.label}
            </h2>
            <ul>
              {group.rows.map((row) => (
                <Row key={row.id} row={row} onRestore={() => putBack(row)} />
              ))}
            </ul>
          </section>
        ))}

        {rows && rows.length >= limit && (
          <Button variant="ghost" size="md" fullWidth onClick={() => setLimit(limit + PAGE_SIZE)}>
            Show more
          </Button>
        )}
      </main>
    </div>
  )
}
