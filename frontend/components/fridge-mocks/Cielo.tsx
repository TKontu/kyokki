'use client'

/**
 * Cielo (Q17-M): a tall pastel-blue fridge with the freezer as a pulled-out drawer at the
 * bottom and the door swung open to the left, dairy in the door; a painted larder on its
 * right, and the going-stale shelf as a column down the left side.
 */

import React from 'react'
import { Basket, Bottle, Defs, DoorBin, Drawer, GlassShelf, Handle, Hinge, Jar } from './parts'
import {
  AreaRegion,
  Canvas,
  Drawing,
  StaleShelf,
  roundedPath,
  useFridge,
  useSvgIds,
  type Box,
  type FridgeMockProps,
} from './shared'
import type { AreaId } from '@/lib/fridge'

const W = 840
const H = 720

const BOX: Record<AreaId, Box> = {
  meat: { x: 218, y: 214, w: 334, h: 72 },
  veggies: { x: 218, y: 292, w: 164, h: 170 },
  fruits: { x: 388, y: 292, w: 164, h: 170 },
  dairy: { x: 34, y: 66, w: 130, h: 128 },
  bread: { x: 212, y: 40, w: 346, h: 80 },
  ready_meals: { x: 212, y: 126, w: 346, h: 80 },
  drinks: { x: 34, y: 300, w: 130, h: 156 },
  pantry: { x: 628, y: 92, w: 182, h: 438 },
  freezer: { x: 222, y: 506, w: 326, h: 112 },
  other: { x: 628, y: 572, w: 182, h: 118 },
}

const LAYOUT: Partial<Record<AreaId, 'column'>> = {
  veggies: 'column',
  fruits: 'column',
  dairy: 'column',
  drinks: 'column',
  pantry: 'column',
  other: 'column',
}

const BLUE = 'fill-[#bcdbe9] stroke-[#9cc4d6] dark:fill-[#7fa3b5] dark:stroke-[#5f8497]'
const LINER = 'fill-[#f6fafc] dark:fill-[#30353b]'
const INSIDE = 'fill-[#fdfeff] dark:fill-[#292c31]'
const ICE = 'fill-[#e1f0f8] dark:fill-[#1b2d38]'
const LARDER = 'fill-[#eef1f2] stroke-[#d5dbde] dark:fill-[#3a4046] dark:stroke-[#4a5259]'
const LARDER_INSIDE = 'fill-[#fbfaf7] dark:fill-[#2c3035]'
const SHELF = 'fill-[#d9dfe2] dark:fill-[#4c545b]'

export function Cielo({ items, onConsume, onMore, onClearExpired }: FridgeMockProps) {
  const { view, byId, hasOther } = useFridge(items)
  const ids = useSvgIds('chromeX', 'chromeY', 'gloss', 'glass')

  return (
    <div data-testid="fridge-mock-cielo" className="flex h-full min-h-0 flex-row gap-3">
      <StaleShelf
        items={view.goingStale}
        expired={view.expired}
        onConsume={onConsume}
        onMore={onMore}
        onClearExpired={onClearExpired}
        orientation="column"
        className="border-2 border-sky-200 bg-sky-50 dark:border-sky-900 dark:bg-slate-900"
        accentClassName="text-rose-700 dark:text-rose-300"
      />
      <Canvas width={W} height={H}>
        <Drawing width={W} height={H}>
          <Defs ids={ids} />
          {/* Floor */}
          <rect x={0} y={700} width={W} height={20} rx={4} className="fill-[#e3e8ea] dark:fill-[#24262b]" />
          <ellipse cx={385} cy={704} rx={220} ry={7} className="fill-black/15 dark:fill-black/40" />

          {/* The door, swung open to the left */}
          <Handle box={{ x: 8, y: 150, w: 12, h: 160 }} ids={ids} />
          <path d={roundedPath({ x: 20, y: 22, w: 156, h: 452 }, 44, 10)} className={BLUE} strokeWidth={2} />
          <path d={roundedPath({ x: 34, y: 38, w: 130, h: 424 }, 32, 8)} className={LINER} />
          <DoorBin box={{ x: 38, y: 66, w: 122, h: 128 }}>
            <Bottle x={112} base={180} w={30} h={84} className="fill-white stroke-slate-200 dark:fill-slate-200/80 dark:stroke-slate-500" capClassName="fill-sky-500" />
            <rect x={48} y={150} width={50} height={30} rx={4} className="fill-yellow-100 dark:fill-yellow-200/60" />
          </DoorBin>
          <DoorBin box={{ x: 38, y: 212, w: 122, h: 70 }}>
            <Bottle x={50} base={272} w={18} h={48} className="fill-red-500 dark:fill-red-600" capClassName="fill-white dark:fill-slate-300" />
            <Bottle x={76} base={272} w={16} h={42} className="fill-yellow-400 dark:fill-yellow-500" capClassName="fill-red-600" />
            <Jar x={102} base={272} w={30} h={34} className="fill-amber-600/70 dark:fill-amber-700/60" />
          </DoorBin>
          <DoorBin box={{ x: 38, y: 300, w: 122, h: 156 }}>
            <Bottle x={46} base={440} w={30} h={96} className="fill-emerald-400/70 dark:fill-emerald-500/40" capClassName="fill-emerald-700" />
            <Bottle x={84} base={440} w={30} h={86} className="fill-orange-300 dark:fill-orange-400/60" capClassName="fill-orange-600" />
            <Bottle x={122} base={440} w={30} h={100} className="fill-sky-200/90 dark:fill-sky-300/40" capClassName="fill-sky-600" />
          </DoorBin>
          <Hinge x={176} y={50} ids={ids} />
          <Hinge x={176} y={440} ids={ids} />

          {/* Body */}
          <rect x={214} y={690} width={22} height={14} rx={4} fill={`url(#${ids.chromeX})`} />
          <rect x={534} y={690} width={22} height={14} rx={4} fill={`url(#${ids.chromeX})`} />
          <path d={roundedPath({ x: 192, y: 14, w: 386, h: 680 }, 64, 24)} className={BLUE} strokeWidth={2} />
          <path d={roundedPath({ x: 192, y: 14, w: 386, h: 680 }, 64, 24)} fill={`url(#${ids.gloss})`} />
          <path d={roundedPath({ x: 212, y: 36, w: 346, h: 432 }, 46, 14)} className={INSIDE} />
          <ellipse cx={385} cy={46} rx={110} ry={10} className="fill-amber-50 dark:fill-amber-100/10" />
          <GlassShelf x={212} y={123} w={346} ids={ids} />
          <GlassShelf x={212} y={209} w={346} ids={ids} />
          <Drawer box={BOX.meat} tint="fill-rose-100/70 stroke-rose-200 dark:fill-rose-300/10 dark:stroke-rose-300/20" />
          <Drawer box={BOX.veggies} tint="fill-green-100/80 stroke-green-200 dark:fill-green-300/10 dark:stroke-green-300/20" />
          <Drawer box={BOX.fruits} tint="fill-amber-100/80 stroke-amber-200 dark:fill-amber-300/10 dark:stroke-amber-300/20" />
          <rect x={202} y={478} width={366} height={5} rx={2} fill={`url(#${ids.chromeY})`} />

          {/* Freezer drawer, pulled out */}
          <path d={roundedPath({ x: 216, y: 496, w: 338, h: 126 }, 10, 4)} className={ICE} />
          <path d={roundedPath({ x: 216, y: 496, w: 338, h: 126 }, 10, 4)} className="fill-none stroke-sky-200 dark:stroke-sky-300/20" strokeWidth={2} />
          {[260, 310, 360, 410, 460, 510].map((x) => (
            <line key={x} x1={x} x2={x} y1={560} y2={620} className="stroke-sky-100 dark:stroke-sky-300/10" strokeWidth={2} />
          ))}
          <path d={roundedPath({ x: 204, y: 618, w: 362, h: 80 }, 10, 20)} className={BLUE} strokeWidth={2} />
          <path d={roundedPath({ x: 204, y: 618, w: 362, h: 80 }, 10, 20)} fill={`url(#${ids.gloss})`} />
          <Handle box={{ x: 300, y: 636, w: 170, h: 12 }} ids={ids} />
          <text
            x={385}
            y={682}
            textAnchor="middle"
            className="fill-white/80 dark:fill-white/50"
            style={{ font: 'italic 700 20px Georgia, serif' }}
          >
            Kyokki
          </text>

          {/* Larder */}
          <rect x={604} y={40} width={230} height={22} rx={6} className={SHELF} />
          <rect x={612} y={58} width={214} height={642} rx={10} className={LARDER} strokeWidth={2} />
          <rect x={628} y={92} width={182} height={438} rx={6} className={LARDER_INSIDE} />
          {[200, 310, 420].map((y) => (
            <rect key={y} x={628} y={y} width={182} height={7} className={SHELF} />
          ))}
          <Jar x={764} base={200} w={28} h={38} className="fill-amber-300/80 dark:fill-amber-500/50" lidClassName="fill-sky-500 dark:fill-sky-700" />
          <Jar x={770} base={310} w={24} h={30} className="fill-slate-300 dark:fill-slate-500" />
          <Bottle x={772} base={420} w={18} h={52} className="fill-lime-700/60 dark:fill-lime-600/40" />
          <rect x={740} y={492} width={58} height={38} rx={8} className="fill-[#e9dcc3] dark:fill-[#4d4538]" />
          <rect x={620} y={538} width={198} height={6} rx={3} className={SHELF} />
          {hasOther ? (
            <>
              <rect x={628} y={552} width={182} height={138} rx={6} className={LARDER_INSIDE} />
              <Basket box={{ x: 700, y: 618, w: 100, h: 68 }} />
            </>
          ) : (
            <>
              <rect x={628} y={552} width={182} height={138} rx={6} className={LARDER} strokeWidth={2} />
              <circle cx={718} cy={574} r={6} fill={`url(#${ids.chromeY})`} />
            </>
          )}
        </Drawing>

        {view.areas
          .filter(({ area, items: inArea }) => area.id !== 'other' || inArea.length > 0)
          .map(({ area }) => (
            <AreaRegion
              key={area.id}
              area={area}
              items={byId[area.id].items}
              box={BOX[area.id]}
              width={W}
              height={H}
              layout={LAYOUT[area.id] ?? 'row'}
              radius={area.id === 'bread' ? 'rounded-t-[2.5rem] rounded-b-lg' : 'rounded-xl'}
              center={area.id === 'bread'}
            />
          ))}
      </Canvas>
    </div>
  )
}

export default Cielo
