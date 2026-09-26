'use client'

/**
 * One area of the fridge, laid over its part of the drawing (Q17-B).
 *
 * FridgeView's contract: a `<section aria-label>` per area, the whole of it an "Open X" link to
 * the area's grid, a few emoji of what is inside and one image of dots - one per item, in its
 * staleness colour. Everything here is sized in the drawing's units (`cqw` of the canvas), so it
 * scales with the drawing and `dotCapacity` knows how many dots fit. An area holding more than
 * that shows a "+" marker in the last slot instead of cutting its dots off; an empty one says
 * "Empty". No numbers.
 */

import Link from 'next/link'
import type { CSSProperties } from 'react'
import type { Area } from '@/lib/fridge'
import { STALENESS, stalenessOf } from '@/lib/staleness'
import type { InventoryItem } from '@/types/inventory'
import { DOT, DOT_GAP, HEADER, PAD, dotCapacity, dotSlot, fitDots } from './capacity'
import type { Box } from './drawing'

export interface AreaSpotProps {
  area: Area
  items: InventoryItem[]
  /** Where it sits, in the drawing's units. */
  box: Box
  /** The drawing's size, to place the box and scale what is in it. */
  width: number
  height: number
  maxEmoji?: number
  /** Rounds the focus ring and the press to the shape drawn beneath. */
  radius?: string
}

const pct = (part: number, whole: number) => `${(part / whole) * 100}%`

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

export function AreaSpot({
  area,
  items,
  box,
  width,
  height,
  maxEmoji = 3,
  radius = 'rounded-xl',
}: AreaSpotProps) {
  // A length in the drawing's units, as a share of the canvas's width
  const u = (units: number) => `calc(${units} * 100cqw / ${width})`
  const place: CSSProperties = {
    left: pct(box.x, width),
    top: pct(box.y, height),
    width: pct(box.w, width),
    height: pct(box.h, height),
  }
  const contents = contentsOf(items, maxEmoji)
  const { shown, more } = fitDots(items, dotCapacity(box))
  const at = (index: number): CSSProperties => {
    const { left, top } = dotSlot(index, box)
    return { left: u(left), top: u(top), width: u(DOT), height: u(DOT) }
  }

  return (
    <section aria-label={area.label} className="absolute" style={place}>
      <Link
        href={`/area/${area.id}`}
        aria-label={`Open ${area.label}`}
        style={{ padding: u(PAD), gap: u(DOT_GAP) }}
        className={
          `absolute inset-0 flex flex-col overflow-hidden transition-colors ${radius} ` +
          'hover:bg-white/20 active:bg-black/10 dark:hover:bg-white/5 dark:active:bg-white/10 ' +
          'focus:outline-none focus-visible:ring-4 focus-visible:ring-primary-400'
        }
      >
        <span
          className="flex shrink-0 items-center overflow-hidden whitespace-nowrap"
          style={{ height: u(HEADER - DOT_GAP), gap: u(4) }}
        >
          <span
            className="rounded-full bg-white/85 font-semibold leading-tight text-slate-800 shadow-sm dark:bg-slate-950/75 dark:text-slate-100"
            style={{ fontSize: u(13), padding: `${u(2)} ${u(7)}` }}
          >
            {area.label}
          </span>
          {contents.length > 0 && (
            <span
              aria-hidden="true"
              className="flex leading-none drop-shadow-sm"
              style={{ fontSize: u(17), gap: u(2) }}
            >
              {contents.map((icon) => (
                <span key={icon}>{icon}</span>
              ))}
            </span>
          )}
        </span>
        {items.length === 0 ? (
          <span
            className="italic text-slate-500 dark:text-slate-400"
            style={{ fontSize: u(12), paddingLeft: u(4) }}
          >
            Empty
          </span>
        ) : (
          // Each dot is placed in its slot (`dotSlot`), not flowed, so what fits is exact
          <span
            role="img"
            aria-label={items
              .map((item) => `${item.product_name} ${STALENESS[stalenessOf(item)].label}`)
              .join(', ')}
            className="pointer-events-none absolute inset-0"
          >
            {shown.map((item, index) => (
              <span
                key={item.id}
                style={at(index)}
                className={`absolute rounded-full shadow-sm ring-2 ring-white/90 dark:ring-black/50 ${STALENESS[stalenessOf(item)].dot}`}
              />
            ))}
            {more && (
              <span
                data-testid="more-dots"
                title="More inside"
                style={{ ...at(shown.length), fontSize: u(13) }}
                className={
                  'absolute flex items-center justify-center rounded-full bg-white font-bold ' +
                  'leading-none text-slate-800 shadow-sm ring-2 ring-slate-500 ' +
                  'dark:bg-slate-900 dark:text-slate-100 dark:ring-slate-300'
                }
              >
                +
              </span>
            )}
          </span>
        )}
      </Link>
    </section>
  )
}

export default AreaSpot
