/**
 * The drawn parts of the fridge (Q17-M; shared with the production fridge since Q17-B):
 * chrome, glass shelves, drawers, door bins, the bread basket, Other's crate and the odd bottle. All decoration - they sit inside a drawing that is `aria-hidden` - and
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

/**
 * A glass shelf seen edge-on: a pale pane behind a light wood front trim (Q29: the shelves are
 * light wood; the pane keeps the fridge looking like a fridge).
 */
export function GlassShelf({ x, y, w, ids }: { x: number; y: number; w: number; ids: PartIds }) {
  return (
    <g>
      <rect x={x} y={y - 5} width={w} height={6} fill={`url(#${ids.glass})`} opacity={0.85} />
      <line x1={x} x2={x + w} y1={y - 5} y2={y - 5} className="stroke-white dark:stroke-sky-200/60" strokeWidth={1.5} />
      <rect
        x={x}
        y={y + 1}
        width={w}
        height={5}
        rx={1.5}
        className="fill-fridge-wood stroke-fridge-wood-edge"
        strokeWidth={1}
      />
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

/**
 * A wicker basket standing on `box`'s bottom edge. The production fridge keeps bread in one on
 * the larder (Q23); the mocks use it for Other. `loaves` puts a loaf and a baguette in it,
 * peeking over the rim.
 */
export function Basket({ box, loaves = false }: { box: Box; loaves?: boolean }) {
  const { x, y, w, h } = box
  const inset = w * 0.08
  return (
    <g>
      {loaves && (
        <g className="fill-[#e0a560] stroke-[#b97a3a] dark:fill-[#a7743f] dark:stroke-[#7a5228]" strokeWidth={1.5}>
          <path d={`M${x + w * 0.12},${y + h * 0.36} L${x + w * 0.5},${y + h * 0.02} L${x + w * 0.6},${y + h * 0.12} L${x + w * 0.26},${y + h * 0.4} Z`} strokeLinejoin="round" />
          <ellipse cx={x + w * 0.66} cy={y + h * 0.3} rx={w * 0.2} ry={h * 0.17} />
        </g>
      )}
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

/** A wooden crate standing on `box`'s bottom edge: Other, at the larder's foot. */
export function Crate({ box }: { box: Box }) {
  const { x, y, w, h } = box
  const slat = h / 3
  return (
    <g className="fill-[#dcc39a] stroke-[#a8875a] dark:fill-[#6e5a3e] dark:stroke-[#4f3f2a]" strokeWidth={2}>
      {[0, 1, 2].map((row) => (
        <rect key={row} x={x} y={y + row * slat + 1} width={w} height={slat - 3} rx={2} />
      ))}
      <rect x={x + 4} y={y} width={8} height={h} rx={1} />
      <rect x={x + w - 12} y={y} width={8} height={h} rx={1} />
    </g>
  )
}

/**
 * A wooden upright (Q41): a light wood post with a few faint grain lines. `part` names the
 * post itself (`data-part`).
 */
export function WoodPost({ box, part }: { box: Box; part?: string }) {
  const { x, y, w, h } = box
  const grain = w >= 10 ? [0.3, 0.68] : [0.5]
  return (
    <g>
      <rect
        data-part={part}
        x={x}
        y={y}
        width={w}
        height={h}
        rx={2}
        className="fill-fridge-wood stroke-fridge-wood-edge"
        strokeWidth={1}
      />
      {grain.map((t, index) => (
        <path
          key={t}
          d={`M${x + w * t},${y + 6} Q${x + w * t + (index % 2 ? -1.5 : 1.5)},${y + h / 2} ${x + w * t},${y + h - 6}`}
          className="fill-none stroke-fridge-wood-edge/50"
          strokeWidth={0.8}
        />
      ))}
    </g>
  )
}

/**
 * One monstera leaf in its own units: its stem meets it at the origin (the heart's notch) and
 * the tip points up, about 1.75 units away.
 */
const LEAF_PATH =
  'M0,0 C-0.3,0.35 -1.05,0.2 -1.05,-0.5 C-1.05,-1.15 -0.45,-1.55 0.04,-1.75 ' +
  'C0.5,-1.5 1.05,-1.15 1.05,-0.5 C1.05,0.2 0.3,0.35 0,0 Z'
/** The splits, from near the midrib out past the edge, on the right; the left mirrors them. */
const LEAF_SPLITS = [
  [0.3, -0.12, 1.2, 0.3],
  [0.32, -0.48, 1.25, -0.3],
  [0.3, -0.9, 1.2, -0.98],
  [0.22, -1.3, 0.85, -1.7],
] as const
/** The side veins, between the splits. */
const LEAF_VEINS = [
  [0.04, -0.3, 0.85, -0.12],
  [0.04, -0.7, 0.95, -0.62],
  [0.04, -1.1, 0.75, -1.3],
] as const
const LEAF_TINTS = [
  'fill-emerald-600 dark:fill-emerald-800',
  'fill-green-600 dark:fill-green-800',
  'fill-emerald-500 dark:fill-emerald-700',
]

/** Where each leaf meets its stem, its size, and its turn from upright: back to front. */
const LEAVES = [
  { x: 690, y: 100, size: 44, turn: -8 },
  { x: 650, y: 150, size: 38, turn: -42 },
  { x: 728, y: 140, size: 36, turn: 36 },
  { x: 706, y: 186, size: 30, turn: 70 },
  { x: 668, y: 196, size: 28, turn: -74 },
] as const

/** Cuts a leaf's splits and two holes, in the leaf's own units. */
function LeafMask({ id }: { id: string }) {
  return (
    <mask id={id} maskUnits="userSpaceOnUse" maskContentUnits="userSpaceOnUse" x={-2} y={-3} width={4} height={4}>
      <rect x={-2} y={-3} width={4} height={4} fill="white" />
      {LEAF_SPLITS.flatMap(([x1, y1, x2, y2]) =>
        [1, -1].map((side) => (
          <line
            key={`${side}${y1}`}
            x1={side * x1}
            y1={y1}
            x2={side * x2}
            y2={y2}
            stroke="black"
            strokeWidth={0.11}
            strokeLinecap="round"
          />
        ))
      )}
      <ellipse cx={0.62} cy={-0.7} rx={0.07} ry={0.1} fill="black" />
      <ellipse cx={-0.62} cy={-0.7} rx={0.07} ry={0.1} fill="black" />
    </mask>
  )
}

/**
 * A *Monstera deliciosa* in a terracotta pot (Q42): the pot stands on `base`, centred on `potX`,
 * and large split, heart-shaped leaves on long stems rise above it. Flat greens with a lighter
 * midrib and veins, a shade deeper in the dark theme. `maskId` must be unique per drawing.
 */
export function Monstera({ potX, base, maskId }: { potX: number; base: number; maskId: string }) {
  const rimY = base - 124
  const stemY = rimY + 4
  return (
    <g>
      <defs>
        <LeafMask id={maskId} />
      </defs>
      {LEAVES.map((leaf) => (
        <path
          key={`stem-${leaf.x}-${leaf.y}`}
          d={`M${potX + (leaf.x - potX) * 0.15},${stemY} Q${(potX + leaf.x) / 2},${(stemY + leaf.y) / 2 + 12} ${leaf.x},${leaf.y}`}
          className="fill-none stroke-green-700 dark:stroke-green-900"
          strokeWidth={3}
          strokeLinecap="round"
        />
      ))}
      {LEAVES.map((leaf, index) => (
        <g
          key={`leaf-${leaf.x}-${leaf.y}`}
          transform={`translate(${leaf.x} ${leaf.y}) rotate(${leaf.turn}) scale(${leaf.size})`}
        >
          <g mask={`url(#${maskId})`}>
            <path d={LEAF_PATH} className={LEAF_TINTS[index % LEAF_TINTS.length]} />
            <g className="fill-none stroke-lime-200/80 dark:stroke-lime-300/40" strokeLinecap="round">
              <path d="M0,0 Q0.06,-0.9 0.04,-1.7" strokeWidth={0.05} />
              {LEAF_VEINS.flatMap(([x1, y1, x2, y2]) =>
                [1, -1].map((side) => (
                  <line
                    key={`${side}${y1}`}
                    x1={side * x1}
                    y1={y1}
                    x2={side * x2}
                    y2={y2}
                    strokeWidth={0.025}
                  />
                ))
              )}
            </g>
          </g>
        </g>
      ))}
      {/* The pot: a tapering body, a rim, a little soil */}
      <path
        d={`M${potX - 30},${rimY + 10} L${potX + 30},${rimY + 10} L${potX + 24},${base} L${potX - 24},${base} Z`}
        className="fill-[#e0a07a] stroke-[#b8754f] dark:fill-[#8a5a42] dark:stroke-[#5f3c2b]"
        strokeWidth={2}
        strokeLinejoin="round"
      />
      <rect
        x={potX - 36}
        y={rimY}
        width={72}
        height={14}
        rx={4}
        className="fill-[#e8b08c] stroke-[#b8754f] dark:fill-[#9a6650] dark:stroke-[#5f3c2b]"
        strokeWidth={2}
      />
      <ellipse cx={potX} cy={rimY + 2} rx={30} ry={3} className="fill-[#6b4a32] dark:fill-[#3a2a1e]" />
    </g>
  )
}
