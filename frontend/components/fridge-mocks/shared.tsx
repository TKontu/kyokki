'use client'

/**
 * What every fridge mock shares (Q17-M): the drawing's canvas, an area as a region of the
 * drawing, its staleness dots, and the going-stale shelf.
 *
 * A mock is an inline SVG drawn in its own units plus HTML regions laid over it at the same
 * coordinates, so the drawing is decoration (hidden from screen readers) and the regions carry
 * FridgeView's contract: a `<section aria-label>` per area in `AREAS` order, an "Open X" link,
 * and one image of dots. Nothing here shows a number.
 */

import Link from 'next/link'
import React from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { IngredientTile } from '@/components/inventory/IngredientTile'
import { buildFridgeView, type Area, type AreaId } from '@/lib/fridge'
import { STALENESS, stalenessOf } from '@/lib/staleness'
import type { InventoryItem } from '@/types/inventory'

export interface FridgeMockProps {
  items: InventoryItem[]
  /** A tap on a shelf tile: the item is used up. */
  onConsume?: (id: string) => void
  onMore?: (id: string) => void
  /** Offered on the shelf when something is past its date. */
  onClearExpired?: (items: InventoryItem[]) => void
}

export interface FridgeMock {
  id: string
  name: string
  /** One line for the switcher. */
  description: string
  Component: React.ComponentType<FridgeMockProps>
}

/** A box in the drawing's own units (its viewBox). */
export interface Box {
  x: number
  y: number
  w: number
  h: number
}

/** An SVG path for a box with its own top and bottom corner radii. */
export function roundedPath({ x, y, w, h }: Box, top: number, bottom = top): string {
  return [
    `M${x + top},${y}`,
    `H${x + w - top}`,
    `A${top},${top} 0 0 1 ${x + w},${y + top}`,
    `V${y + h - bottom}`,
    `A${bottom},${bottom} 0 0 1 ${x + w - bottom},${y + h}`,
    `H${x + bottom}`,
    `A${bottom},${bottom} 0 0 1 ${x},${y + h - bottom}`,
    `V${y + top}`,
    `A${top},${top} 0 0 1 ${x + top},${y}`,
    'Z',
  ].join(' ')
}

/** The ids an SVG's gradients need, unique per drawing on the page. */
export function useSvgIds<K extends string>(...names: K[]): Record<K, string> {
  const base = React.useId().replace(/[^a-zA-Z0-9_-]/g, '')
  return Object.fromEntries(names.map((name) => [name, `${base}-${name}`])) as Record<K, string>
}

/** What a mock draws from: the areas by id, the shelf, and what the shelf may clear. */
export function useFridge(items: InventoryItem[]) {
  const view = React.useMemo(() => buildFridgeView(items), [items])
  const byId = Object.fromEntries(view.areas.map((entry) => [entry.area.id, entry])) as Record<
    AreaId,
    { area: Area; items: InventoryItem[] }
  >
  return { view, byId, hasOther: byId.other.items.length > 0 }
}

/**
 * The drawing's frame: as large as the space allows at the drawing's own aspect ratio, and
 * never larger, so the whole fridge is on screen without scrolling.
 */
export function Canvas({
  width,
  height,
  children,
  className = '',
}: {
  width: number
  height: number
  children: ReactNode
  className?: string
}) {
  const style: CSSProperties = {
    width: `min(100cqw, calc(100cqh * ${width / height}))`,
    height: `min(100cqh, calc(100cqw * ${height / width}))`,
  }
  return (
    <div className={`relative min-h-0 min-w-0 flex-1 [container-type:size] ${className}`}>
      <div className="absolute inset-0 m-auto" style={style}>
        {children}
      </div>
    </div>
  )
}

/** The decorative drawing under the regions. */
export function Drawing({
  width,
  height,
  children,
}: {
  width: number
  height: number
  children: ReactNode
}) {
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      focusable="false"
      className="absolute inset-0 h-full w-full overflow-visible"
    >
      {children}
    </svg>
  )
}

export function Dots({ items }: { items: InventoryItem[] }) {
  if (items.length === 0) return null
  return (
    <div
      role="img"
      aria-label={items
        .map((item) => `${item.product_name} ${STALENESS[stalenessOf(item)].label}`)
        .join(', ')}
      className="flex flex-wrap gap-1"
    >
      {items.map((item) => (
        <span
          key={item.id}
          className={`h-3 w-3 rounded-full shadow-sm ring-2 ring-white/90 dark:ring-black/50 ${STALENESS[stalenessOf(item)].dot}`}
        />
      ))}
    </div>
  )
}

/** A few emoji of what is inside: each kind once, stalest first. */
function contentsOf(items: InventoryItem[], max: number): string[] {
  const seen: string[] = []
  for (const item of items) {
    const icon = item.category_icon
    if (icon && !seen.includes(icon)) seen.push(icon)
    if (seen.length === max) break
  }
  return seen
}

export interface AreaRegionProps {
  area: Area
  items: InventoryItem[]
  /** Where it sits, in the drawing's units. */
  box: Box
  /** The drawing's size, to turn the box into percentages. */
  width: number
  height: number
  /** A shallow shelf reads in one line; a tall drawer stacks label, contents and dots. */
  layout?: 'row' | 'column'
  maxEmoji?: number
  /** Rounds the focus ring and the press to the shape drawn beneath. */
  radius?: string
  /** Centre the contents, for a region whose corners are too round to start in. */
  center?: boolean
}

const pct = (part: number, whole: number) => `${(part / whole) * 100}%`

/** One area: a region of the drawing, and the whole of it the link to the area's grid. */
export function AreaRegion({
  area,
  items,
  box,
  width,
  height,
  layout = 'row',
  maxEmoji = 4,
  radius = 'rounded-xl',
  center = false,
}: AreaRegionProps) {
  const style: CSSProperties = {
    left: pct(box.x, width),
    top: pct(box.y, height),
    width: pct(box.w, width),
    height: pct(box.h, height),
  }
  const contents = contentsOf(items, maxEmoji)
  const column = layout === 'column'
  return (
    <section aria-label={area.label} className="absolute" style={style}>
      <Link
        href={`/area/${area.id}`}
        aria-label={`Open ${area.label}`}
        className={
          `absolute inset-0 flex overflow-hidden p-1.5 transition-colors ${radius} ` +
          'hover:bg-white/20 active:bg-black/10 dark:hover:bg-white/5 dark:active:bg-white/10 ' +
          'focus:outline-none focus-visible:ring-4 focus-visible:ring-primary-400 ' +
          (column
            ? `flex-col gap-1.5 ${center ? 'items-center pt-4' : 'items-start'}`
            : 'flex-row flex-wrap items-center gap-x-2 gap-y-1 ' +
              (center ? 'content-center justify-center' : 'content-start'))
        }
      >
        <span className="rounded-full bg-white/85 px-2 py-0.5 text-xs font-semibold text-slate-800 shadow-sm dark:bg-slate-950/75 dark:text-slate-100">
          {area.label}
        </span>
        {contents.length > 0 && (
          <span
            aria-hidden="true"
            className="flex gap-0.5 text-xl leading-none drop-shadow-sm"
          >
            {contents.map((icon) => (
              <span key={icon}>{icon}</span>
            ))}
          </span>
        )}
        <Dots items={items} />
      </Link>
    </section>
  )
}

export interface StaleShelfProps {
  items: InventoryItem[]
  expired: InventoryItem[]
  onConsume?: (id: string) => void
  onMore?: (id: string) => void
  onClearExpired?: (items: InventoryItem[]) => void
  /** A strip across the top, or a column down the side. */
  orientation: 'row' | 'column'
  /** The variant's finish for the shelf. */
  className?: string
  /** Colour of the heading and the clear link, to suit the finish. */
  accentClassName?: string
}

/** What is going stale, as tiles to tap - FridgeView's shelf, set where the design wants it. */
export function StaleShelf({
  items,
  expired,
  onConsume,
  onMore,
  onClearExpired,
  orientation,
  className = '',
  accentClassName = 'text-red-700 dark:text-red-300',
}: StaleShelfProps) {
  if (items.length === 0) return null
  const row = orientation === 'row'
  return (
    <section
      aria-label="Going stale"
      className={
        `flex min-h-0 shrink-0 flex-col gap-2 rounded-3xl p-3 ${className} ` +
        (row ? 'w-full' : 'h-full w-56')
      }
    >
      <h2 className={`flex items-center gap-2 text-base font-semibold ${accentClassName}`}>
        Going stale
        {onClearExpired && expired.length > 0 && (
          <button
            type="button"
            onClick={() => onClearExpired(expired)}
            className="ml-auto min-h-touch text-sm font-medium underline"
          >
            Clear expired
          </button>
        )}
      </h2>
      <ul
        className={
          row
            ? 'grid auto-cols-[minmax(5.5rem,1fr)] grid-flow-col gap-2 overflow-x-auto pb-1'
            : 'grid min-h-0 flex-1 auto-rows-min grid-cols-2 content-start gap-2 overflow-y-auto pr-1'
        }
      >
        {items.map((item) => (
          <li key={item.id}>
            <IngredientTile item={item} onSelect={onConsume} onMore={onMore} />
          </li>
        ))}
      </ul>
    </section>
  )
}
