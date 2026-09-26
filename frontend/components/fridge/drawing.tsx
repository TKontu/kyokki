'use client'

/**
 * How a fridge is drawn (Q17-M, shared with the production fridge since Q17-B): an inline SVG
 * in its own units, inside a frame that keeps the drawing's aspect ratio and fits the space it
 * is given, so the whole fridge is on screen without scrolling.
 */

import React from 'react'
import type { CSSProperties, ReactNode } from 'react'

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

/**
 * The drawing's frame: as large as the space allows at the drawing's own aspect ratio, and
 * never larger. The frame is itself a size container, so what is laid over the drawing can be
 * sized in the drawing's units (`cqw`) and scale with it.
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
        {/* The container is a layer inside the frame: the frame's own size is in `cq` units of
            the outer box, and an element cannot size itself by its own container units */}
        <div className="absolute inset-0 [container-type:size]">{children}</div>
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
