/**
 * The drawn parts of the fridge (Q17-M; shared with the production fridge since Q17-B):
 * chrome, glass shelves, drawers, door bins and the odd bottle. All decoration - they sit inside a drawing that is `aria-hidden` - and
 * all coloured through Tailwind classes, so each has a light and a dark finish.
 */

import React from 'react'
import { roundedPath, type Box } from './drawing'

export interface PartIds {
  chromeX: string
  chromeY: string
  gloss: string
  glass: string
}

/** Gradients for chrome (along each axis), a finish's gloss and a glass pane. */
export function Defs({ ids }: { ids: PartIds }) {
  return (
    <defs>
      <linearGradient id={ids.chromeX} x1="0" x2="1" y1="0" y2="0">
        <stop offset="0" stopColor="#8d96a1" />
        <stop offset="0.3" stopColor="#f7f9fb" />
        <stop offset="0.55" stopColor="#b9c1ca" />
        <stop offset="0.8" stopColor="#eef1f4" />
        <stop offset="1" stopColor="#7d8793" />
      </linearGradient>
      <linearGradient id={ids.chromeY} x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stopColor="#8d96a1" />
        <stop offset="0.3" stopColor="#f7f9fb" />
        <stop offset="0.55" stopColor="#b9c1ca" />
        <stop offset="0.8" stopColor="#eef1f4" />
        <stop offset="1" stopColor="#7d8793" />
      </linearGradient>
      <linearGradient id={ids.gloss} x1="0" x2="1" y1="0" y2="0.2">
        <stop offset="0" stopColor="#ffffff" stopOpacity="0.55" />
        <stop offset="0.12" stopColor="#ffffff" stopOpacity="0.18" />
        <stop offset="0.5" stopColor="#ffffff" stopOpacity="0" />
        <stop offset="0.9" stopColor="#000000" stopOpacity="0.04" />
        <stop offset="1" stopColor="#000000" stopOpacity="0.12" />
      </linearGradient>
      <linearGradient id={ids.glass} x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stopColor="#ffffff" stopOpacity="0.9" />
        <stop offset="1" stopColor="#bae6fd" stopOpacity="0.5" />
      </linearGradient>
    </defs>
  )
}

/** A chrome bar handle on two stand-offs, upright or across. */
export function Handle({ box, ids }: { box: Box; ids: PartIds }) {
  const upright = box.h > box.w
  const r = Math.min(box.w, box.h) / 2
  return (
    <g>
      {upright ? (
        <>
          <rect x={box.x - 4} y={box.y + 6} width={box.w} height={8} rx={3} fill={`url(#${ids.chromeY})`} />
          <rect x={box.x - 4} y={box.y + box.h - 14} width={box.w} height={8} rx={3} fill={`url(#${ids.chromeY})`} />
        </>
      ) : (
        <>
          <rect x={box.x + 6} y={box.y - 4} width={8} height={box.h} rx={3} fill={`url(#${ids.chromeX})`} />
          <rect x={box.x + box.w - 14} y={box.y - 4} width={8} height={box.h} rx={3} fill={`url(#${ids.chromeX})`} />
        </>
      )}
      <rect
        x={box.x}
        y={box.y}
        width={box.w}
        height={box.h}
        rx={r}
        fill={`url(#${upright ? ids.chromeX : ids.chromeY})`}
        className="stroke-slate-500/40"
        strokeWidth={1}
      />
    </g>
  )
}

/** Small chrome hinge block. */
export function Hinge({ x, y, ids }: { x: number; y: number; ids: PartIds }) {
  return <rect x={x} y={y} width={18} height={14} rx={3} fill={`url(#${ids.chromeY})`} />
}

/** A glass shelf seen edge-on: a pale pane with a bright front edge. */
export function GlassShelf({ x, y, w, ids }: { x: number; y: number; w: number; ids: PartIds }) {
  return (
    <g>
      <rect x={x} y={y - 3} width={w} height={7} fill={`url(#${ids.glass})`} opacity={0.85} />
      <line x1={x} x2={x + w} y1={y - 3} y2={y - 3} className="stroke-white dark:stroke-sky-200/60" strokeWidth={1.5} />
      <line x1={x} x2={x + w} y1={y + 4} y2={y + 4} className="stroke-sky-300/80 dark:stroke-sky-400/40" strokeWidth={1} />
    </g>
  )
}

/**
 * A see-through drawer: its back and sides faint, its front a tinted pane with a finger pull.
 * `tint` colours the front, e.g. green for a crisper.
 */
export function Drawer({ box, tint }: { box: Box; tint: string }) {
  const front = { ...box, y: box.y + box.h * 0.45, h: box.h * 0.55 }
  return (
    <g>
      <path d={roundedPath(box, 8, 10)} className="fill-slate-200/40 stroke-slate-300 dark:fill-white/5 dark:stroke-white/10" strokeWidth={1.5} />
      <path d={roundedPath(front, 6, 10)} className={tint} strokeWidth={1.5} />
      <rect
        x={box.x + box.w / 2 - Math.min(28, box.w / 5)}
        y={front.y + 6}
        width={Math.min(56, (box.w * 2) / 5)}
        height={6}
        rx={3}
        className="fill-black/15 dark:fill-black/40"
      />
    </g>
  )
}

/** A door bin: a trough whose tinted front lip hides the bottom of what stands in it. */
export function DoorBin({ box, children }: { box: Box; children?: React.ReactNode }) {
  const lip = { ...box, y: box.y + box.h * 0.6, h: box.h * 0.4 }
  return (
    <g>
      <rect x={box.x + 4} y={box.y + box.h * 0.2} width={box.w - 8} height={box.h * 0.8} rx={6} className="fill-black/5 dark:fill-white/5" />
      {children}
      <path d={roundedPath(lip, 5, 10)} className="fill-sky-100/70 stroke-sky-200 dark:fill-sky-200/15 dark:stroke-sky-200/20" strokeWidth={1.5} />
      <line x1={lip.x + 6} x2={lip.x + lip.w - 6} y1={lip.y + 5} y2={lip.y + 5} className="stroke-white/80 dark:stroke-white/20" strokeWidth={2} strokeLinecap="round" />
    </g>
  )
}

/** A bottle standing on `base`: body, shoulder, neck and cap. */
export function Bottle({
  x,
  base,
  w,
  h,
  className,
  capClassName = 'fill-slate-500',
}: {
  x: number
  base: number
  w: number
  h: number
  className: string
  capClassName?: string
}) {
  const neck = w * 0.38
  const bodyTop = base - h * 0.62
  return (
    <g>
      <rect x={x} y={bodyTop} width={w} height={h * 0.62} rx={w * 0.2} className={className} />
      <path
        d={`M${x},${bodyTop + 4} Q${x + w / 2},${bodyTop - h * 0.22} ${x + w},${bodyTop + 4} Z`}
        className={className}
      />
      <rect x={x + (w - neck) / 2} y={base - h * 0.92} width={neck} height={h * 0.2} className={className} />
      <rect x={x + (w - neck) / 2 - 1} y={base - h} width={neck + 2} height={h * 0.1} rx={1.5} className={capClassName} />
    </g>
  )
}

/** A jar with a lid, standing on `base`. */
export function Jar({ x, base, w, h, className, lidClassName = 'fill-slate-400' }: {
  x: number
  base: number
  w: number
  h: number
  className: string
  lidClassName?: string
}) {
  return (
    <g>
      <rect x={x} y={base - h * 0.82} width={w} height={h * 0.82} rx={w * 0.22} className={className} />
      <rect x={x + 2} y={base - h} width={w - 4} height={h * 0.2} rx={2} className={lidClassName} />
    </g>
  )
}

/** A row of eggs in the door, for a finish that has room for them. */
export function Eggs({ x, base, count, gap = 20 }: { x: number; base: number; count: number; gap?: number }) {
  return (
    <g>
      {Array.from({ length: count }, (_, index) => (
        <ellipse
          key={index}
          cx={x + index * gap}
          cy={base - 11}
          rx={8}
          ry={11}
          className="fill-[#f6ead6] stroke-[#e2d2b6] dark:fill-[#d9ccb4] dark:stroke-[#b9a98c]"
          strokeWidth={1}
        />
      ))}
    </g>
  )
}

/** A wicker basket for Other, standing on `box`'s bottom edge. */
export function Basket({ box }: { box: Box }) {
  const { x, y, w, h } = box
  const inset = w * 0.08
  return (
    <g>
      <path
        d={`M${x + w * 0.2},${y + h * 0.3} Q${x + w / 2},${y - h * 0.35} ${x + w * 0.8},${y + h * 0.3}`}
        className="fill-none stroke-[#b58b5a] dark:stroke-[#7d5f3e]"
        strokeWidth={5}
        strokeLinecap="round"
      />
      <path
        d={`M${x},${y + h * 0.3} H${x + w} L${x + w - inset},${y + h} H${x + inset} Z`}
        className="fill-[#d7b27f] stroke-[#b58b5a] dark:fill-[#8a6a47] dark:stroke-[#6b4f33]"
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {[0.5, 0.7, 0.88].map((t) => (
        <line
          key={t}
          x1={x + inset * t}
          x2={x + w - inset * t}
          y1={y + h * t}
          y2={y + h * t}
          className="stroke-[#b58b5a]/70 dark:stroke-[#6b4f33]"
          strokeWidth={2}
        />
      ))}
    </g>
  )
}
