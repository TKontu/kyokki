'use client'

/**
 * The fridge on `/` (Q17-B): Cielo, redrawn for the iPad mounted upright (810×1080).
 *
 * The going-stale strip runs across the top. Below it the tall pastel-blue fridge stands in
 * the middle with its door swung open to the left - dairy and drinks in the door bins - and
 * inside, top to bottom: ready meals on the glass shelf, the meat and fish drawer, the veggie
 * and fruit crispers side by side, and the freezer drawer pulled out at the bottom. On the
 * right, under a window, a painted larder: the bread basket on its top (Q23: bread is not
 * kept in the fridge), the pantry on its shelves, and at its foot a crate for Other when
 * something has no area.
 *
 * The drawing is decoration (hidden from screen readers); each area is an `AreaSpot` laid over
 * its part of it at the same coordinates, which carries FridgeView's contract.
 */

import React from 'react'
import { buildFridgeView, type Area, type AreaId } from '@/lib/fridge'
import type { InventoryItem } from '@/types/inventory'
import { AreaSpot } from './AreaSpot'
import { Canvas, Drawing, roundedPath, useSvgIds, type Box } from './drawing'
import { Basket, Bottle, Crate, Defs, DoorBin, Drawer, GlassShelf, Handle, Hinge, Jar } from './parts'
import { StaleStrip } from './StaleStrip'

export interface CieloFridgeProps {
  items: InventoryItem[]
  /** A tap on a going-stale tile: the item is used up. */
  onConsume?: (id: string) => void
  onMore?: (id: string) => void
  /** Offered on the strip when something is past its date. */
  onClearExpired?: (items: InventoryItem[]) => void
}

/**
 * The box the fridge gets on the upright iPad (810×1080 CSS px), measured in Chromium on the
 * sample stock: the width less the page's padding, the height left under the app bar, the slim
 * row of Undo and + Add (Q20: no visible title) and a going-stale strip whose names fit on one
 * line - 778×793 (Chromium reports 793.5). The drawing is drawn to this box's shape. It is
 * near-square - the screen is portrait, the space under the strip is not - so a tall drawing
 * would leave bands. When a long name wraps in the strip, the box is a few pixels shorter and
 * the drawing letterboxes slightly at its sides; it never scrolls.
 */
export const PORTRAIT_BOX = { w: 778, h: 793 }

/** The drawing's units: about a CSS pixel each on the portrait iPad. */
export const CIELO_WIDTH = 780
export const CIELO_HEIGHT = 795

/** Where each area sits in the drawing. No two overlap (tested). */
export const CIELO_BOX: Record<AreaId, Box> = {
  ready_meals: { x: 232, y: 44, w: 340, h: 136 },
  meat: { x: 232, y: 194, w: 340, h: 130 },
  veggies: { x: 232, y: 332, w: 166, h: 188 },
  fruits: { x: 406, y: 332, w: 166, h: 188 },
  freezer: { x: 236, y: 550, w: 332, h: 124 },
  dairy: { x: 30, y: 66, w: 144, h: 204 },
  drinks: { x: 30, y: 372, w: 144, h: 204 },
  bread: { x: 622, y: 212, w: 148, h: 130 },
  pantry: { x: 626, y: 366, w: 136, h: 262 },
  other: { x: 628, y: 644, w: 132, h: 116 },
}

const W = CIELO_WIDTH
const H = CIELO_HEIGHT

const BLUE = 'fill-[#bcdbe9] stroke-[#9cc4d6] dark:fill-[#7fa3b5] dark:stroke-[#5f8497]'
const LINER = 'fill-[#f6fafc] dark:fill-[#30353b]'
const INSIDE = 'fill-[#fdfeff] dark:fill-[#292c31]'
const ICE = 'fill-[#e1f0f8] dark:fill-[#1b2d38]'
const LARDER = 'fill-[#eef1f2] stroke-[#d5dbde] dark:fill-[#3a4046] dark:stroke-[#4a5259]'
const LARDER_INSIDE = 'fill-[#fbfaf7] dark:fill-[#2c3035]'
const SHELF = 'fill-[#d9dfe2] dark:fill-[#4c545b]'

function FridgeDrawing({ hasOther }: { hasOther: boolean }) {
  const ids = useSvgIds('chromeX', 'chromeY', 'gloss', 'glass')
  return (
    <Drawing width={W} height={H}>
      <Defs ids={ids} />
      {/* Floor */}
      <rect x={0} y={772} width={W} height={23} rx={4} className="fill-[#e3e8ea] dark:fill-[#24262b]" />
      <ellipse cx={402} cy={776} rx={230} ry={7} className="fill-black/15 dark:fill-black/40" />

      {/* The door, swung open to the left: dairy and drinks in its bins */}
      <Handle box={{ x: 2, y: 190, w: 12, h: 170 }} ids={ids} />
      <path d={roundedPath({ x: 14, y: 28, w: 176, h: 572 }, 44, 12)} className={BLUE} strokeWidth={2} />
      <path d={roundedPath({ x: 28, y: 44, w: 148, h: 540 }, 32, 8)} className={LINER} />
      <DoorBin box={{ x: 32, y: 70, w: 140, h: 196 }}>
        <Bottle x={124} base={252} w={32} h={100} className="fill-white stroke-slate-200 dark:fill-slate-200/80 dark:stroke-slate-500" capClassName="fill-sky-500" />
        <rect x={44} y={214} width={60} height={38} rx={4} className="fill-yellow-100 dark:fill-yellow-200/60" />
        <path d="M50,214 L96,196 L100,214 Z" className="fill-amber-200 dark:fill-amber-300/60" />
      </DoorBin>
      <DoorBin box={{ x: 32, y: 286, w: 140, h: 72 }}>
        <Bottle x={46} base={348} w={18} h={50} className="fill-red-500 dark:fill-red-600" capClassName="fill-white dark:fill-slate-300" />
        <Bottle x={74} base={348} w={16} h={44} className="fill-yellow-400 dark:fill-yellow-500" capClassName="fill-red-600" />
        <Jar x={104} base={348} w={32} h={36} className="fill-amber-600/70 dark:fill-amber-700/60" />
      </DoorBin>
      <DoorBin box={{ x: 32, y: 376, w: 140, h: 196 }}>
        <Bottle x={42} base={556} w={30} h={110} className="fill-emerald-400/70 dark:fill-emerald-500/40" capClassName="fill-emerald-700" />
        <Bottle x={84} base={556} w={30} h={96} className="fill-orange-300 dark:fill-orange-400/60" capClassName="fill-orange-600" />
        <Bottle x={126} base={556} w={30} h={116} className="fill-sky-200/90 dark:fill-sky-300/40" capClassName="fill-sky-600" />
      </DoorBin>
      <Hinge x={190} y={56} ids={ids} />
      <Hinge x={190} y={566} ids={ids} />

      {/* Body */}
      <rect x={226} y={758} width={22} height={16} rx={4} fill={`url(#${ids.chromeX})`} />
      <rect x={556} y={758} width={22} height={16} rx={4} fill={`url(#${ids.chromeX})`} />
      <path d={roundedPath({ x: 208, y: 12, w: 388, h: 750 }, 64, 24)} className={BLUE} strokeWidth={2} />
      <path d={roundedPath({ x: 208, y: 12, w: 388, h: 750 }, 64, 24)} fill={`url(#${ids.gloss})`} />
      <path d={roundedPath({ x: 226, y: 34, w: 352, h: 496 }, 46, 14)} className={INSIDE} />
      <ellipse cx={402} cy={44} rx={110} ry={9} className="fill-amber-50 dark:fill-amber-100/10" />
      {/* One glass shelf: ready meals have the top of the fridge since bread moved out (Q23) */}
      <GlassShelf x={226} y={187} w={352} ids={ids} />
      <Drawer box={CIELO_BOX.meat} tint="fill-rose-100/70 stroke-rose-200 dark:fill-rose-300/10 dark:stroke-rose-300/20" />
      <Drawer box={CIELO_BOX.veggies} tint="fill-green-100/80 stroke-green-200 dark:fill-green-300/10 dark:stroke-green-300/20" />
      <Drawer box={CIELO_BOX.fruits} tint="fill-amber-100/80 stroke-amber-200 dark:fill-amber-300/10 dark:stroke-amber-300/20" />
      <rect x={216} y={536} width={372} height={5} rx={2} fill={`url(#${ids.chromeY})`} />

      {/* Freezer drawer, pulled out */}
      <path d={roundedPath({ x: 230, y: 546, w: 344, h: 134 }, 10, 4)} className={ICE} />
      <path d={roundedPath({ x: 230, y: 546, w: 344, h: 134 }, 10, 4)} className="fill-none stroke-sky-200 dark:stroke-sky-300/20" strokeWidth={2} />
      {[276, 326, 376, 426, 476, 526].map((x) => (
        <line key={x} x1={x} x2={x} y1={618} y2={676} className="stroke-sky-100 dark:stroke-sky-300/10" strokeWidth={2} />
      ))}
      <path d={roundedPath({ x: 218, y: 674, w: 368, h: 88 }, 10, 20)} className={BLUE} strokeWidth={2} />
      <path d={roundedPath({ x: 218, y: 674, w: 368, h: 88 }, 10, 20)} fill={`url(#${ids.gloss})`} />
      <Handle box={{ x: 317, y: 692, w: 170, h: 12 }} ids={ids} />
      <text
        x={402}
        y={744}
        textAnchor="middle"
        className="fill-white/80 dark:fill-white/50"
        style={{ font: 'italic 700 20px Georgia, serif' }}
      >
        Kyokki
      </text>

      {/* A window on the wall */}
      <rect x={626} y={24} width={136} height={150} rx={10} className={LARDER} strokeWidth={3} />
      <rect x={638} y={36} width={112} height={126} rx={4} className="fill-sky-100 dark:fill-slate-800" />
      <circle cx={718} cy={66} r={14} className="fill-amber-100 dark:fill-slate-300/40" />
      <rect x={691} y={36} width={6} height={126} className={SHELF} />
      <rect x={638} y={96} width={112} height={6} className={SHELF} />
      <rect x={620} y={172} width={148} height={10} rx={4} className={SHELF} />

      {/* Larder: a painted cupboard to the floor. Bread in its basket on top (Q23), the
          pantry on open shelves, and an open bottom where Other's crate stands */}
      <g data-part="bread-basket">
        <Basket box={{ x: 634, y: 262, w: 124, h: 80 }} loaves />
      </g>
      <rect x={612} y={342} width={164} height={16} rx={6} className={SHELF} />
      <rect x={618} y={356} width={152} height={418} rx={10} className={LARDER} strokeWidth={2} />
      <rect x={628} y={366} width={132} height={398} rx={6} className={LARDER_INSIDE} />
      {[456, 546, 632].map((y) => (
        <rect key={y} x={628} y={y} width={132} height={6} className={SHELF} />
      ))}
      <Jar x={722} base={456} w={26} h={36} className="fill-amber-300/80 dark:fill-amber-500/50" lidClassName="fill-sky-500 dark:fill-sky-700" />
      <Jar x={726} base={546} w={24} h={30} className="fill-slate-300 dark:fill-slate-500" />
      <Bottle x={700} base={546} w={16} h={48} className="fill-lime-700/60 dark:fill-lime-600/40" />
      {hasOther ? (
        <g data-part="other-crate">
          <Crate box={{ x: 640, y: 700, w: 108, h: 62 }} />
        </g>
      ) : (
        <rect x={698} y={726} width={54} height={36} rx={8} className="fill-[#e9dcc3] dark:fill-[#4d4538]" />
      )}
    </Drawing>
  )
}

export function CieloFridge({ items, onConsume, onMore, onClearExpired }: CieloFridgeProps) {
  const view = React.useMemo(() => buildFridgeView(items), [items])
  const byId = Object.fromEntries(view.areas.map((entry) => [entry.area.id, entry])) as Record<
    AreaId,
    { area: Area; items: InventoryItem[] }
  >
  const hasOther = byId.other.items.length > 0

  return (
    <div data-testid="fridge-cielo" className="flex h-full min-h-0 flex-1 flex-col gap-2">
      <StaleStrip
        items={view.goingStale}
        expired={view.expired}
        onConsume={onConsume}
        onMore={onMore}
        onClearExpired={onClearExpired}
      />
      {/* A row around the canvas: Chrome resolves the canvas's `cqh` to nothing when the
          canvas takes its height from a column's flexing, but not when stretched across one */}
      <div className="flex min-h-0 flex-1">
        <Canvas width={W} height={H}>
          <FridgeDrawing hasOther={hasOther} />
          {view.areas
            .filter(({ area, items: inArea }) => area.id !== 'other' || inArea.length > 0)
            .map(({ area, items: inArea }) => (
              <AreaSpot
                key={area.id}
                area={area}
                items={inArea}
                box={CIELO_BOX[area.id]}
                width={W}
                height={H}
                maxEmoji={CIELO_BOX[area.id].w < 200 ? 2 : 3}
              />
            ))}
        </Canvas>
      </div>
    </div>
  )
}

export default CieloFridge
