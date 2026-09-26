'use client'

/**
 * Rosso (Q17-M): a red retro side-by-side, the freezer a full-height column on the left and
 * the fridge door swung open to the right; open pantry shelves beside it, and the going-stale
 * shelf as a column down the right side.
 */

import React from 'react'
import { Basket, Bottle, Defs, DoorBin, Drawer, Eggs, GlassShelf, Handle, Hinge, Jar } from './parts'
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

const W = 1000
const H = 800

const BOX: Record<AreaId, Box> = {
  meat: { x: 464, y: 414, w: 286, h: 104 },
  veggies: { x: 464, y: 526, w: 140, h: 210 },
  fruits: { x: 610, y: 526, w: 140, h: 210 },
  dairy: { x: 458, y: 40, w: 298, h: 118 },
  bread: { x: 458, y: 164, w: 298, h: 118 },
  ready_meals: { x: 458, y: 288, w: 298, h: 118 },
  drinks: { x: 814, y: 420, w: 112, h: 300 },
  pantry: { x: 34, y: 170, w: 182, h: 510 },
  freezer: { x: 284, y: 40, w: 156, h: 704 },
  other: { x: 34, y: 694, w: 182, h: 84 },
}

const LAYOUT: Partial<Record<AreaId, 'column'>> = {
  veggies: 'column',
  fruits: 'column',
  drinks: 'column',
  pantry: 'column',
  freezer: 'column',
  dairy: 'column',
  bread: 'column',
  ready_meals: 'column',
}

const RED = 'fill-[#d9443a] stroke-[#b8342b] dark:fill-[#a3342d] dark:stroke-[#7c2620]'
const LINER = 'fill-[#fbf8f6] dark:fill-[#33353a]'
const INSIDE = 'fill-[#fffdfb] dark:fill-[#2a2c30]'
const ICE = 'fill-[#e2f0f8] dark:fill-[#1b2c37]'
const RACK = 'fill-[#f4efe9] stroke-[#ddd3c7] dark:fill-[#3b3834] dark:stroke-[#56514a]'
const PLANK = 'fill-[#d8cbbb] dark:fill-[#5a5249]'

export function Rosso({ items, onConsume, onMore, onClearExpired }: FridgeMockProps) {
  const { view, byId, hasOther } = useFridge(items)
  const ids = useSvgIds('chromeX', 'chromeY', 'gloss', 'glass')

  return (
    <div data-testid="fridge-mock-rosso" className="flex h-full min-h-0 flex-row gap-3">
      <Canvas width={W} height={H}>
        <Drawing width={W} height={H}>
          <Defs ids={ids} />
          {/* Floor */}
          <rect x={0} y={778} width={W} height={22} rx={4} className="fill-[#ebe3dc] dark:fill-[#25262b]" />
          <ellipse cx={560} cy={780} rx={320} ry={8} className="fill-black/15 dark:fill-black/40" />

          {/* Open pantry shelves */}
          <rect x={20} y={150} width={14} height={630} rx={4} className={PLANK} />
          <rect x={216} y={150} width={14} height={630} rx={4} className={PLANK} />
          <rect x={34} y={170} width={182} height={608} className={RACK} strokeWidth={1.5} />
          {[150, 290, 420, 550, 684].map((y) => (
            <rect key={y} x={14} y={y} width={222} height={10} rx={3} className={PLANK} />
          ))}
          <Jar x={168} base={290} w={30} h={40} className="fill-amber-300/80 dark:fill-amber-500/50" lidClassName="fill-red-600 dark:fill-red-800" />
          <Jar x={134} base={290} w={26} h={30} className="fill-orange-200/90 dark:fill-orange-400/40" />
          <Jar x={172} base={420} w={26} h={34} className="fill-slate-300 dark:fill-slate-500" />
          <Bottle x={176} base={550} w={20} h={58} className="fill-lime-700/60 dark:fill-lime-600/40" />
          <rect x={146} y={640} width={60} height={44} rx={8} className="fill-[#e9dcc3] dark:fill-[#4d4538]" />
          {hasOther && <Basket box={{ x: 110, y: 712, w: 100, h: 66 }} />}

          {/* Freezer door, open towards us */}
          <path d={roundedPath({ x: 238, y: 20, w: 18, h: 740 }, 8, 8)} className={RED} strokeWidth={2} />
          <Handle box={{ x: 240, y: 300, w: 10, h: 160 }} ids={ids} />

          {/* Body */}
          <rect x={290} y={764} width={24} height={16} rx={4} fill={`url(#${ids.chromeX})`} />
          <rect x={726} y={764} width={24} height={16} rx={4} fill={`url(#${ids.chromeX})`} />
          <path d={roundedPath({ x: 262, y: 16, w: 518, h: 754 }, 70, 26)} className={RED} strokeWidth={2} />
          <path d={roundedPath({ x: 262, y: 16, w: 518, h: 754 }, 70, 26)} fill={`url(#${ids.gloss})`} />

          {/* Freezer column */}
          <path d={roundedPath(BOX.freezer, 48, 10)} className={ICE} />
          {[230, 420, 600].map((y) => (
            <g key={y}>
              <rect x={292} y={y} width={140} height={6} rx={3} className="fill-sky-200 dark:fill-sky-300/20" />
              {[310, 340, 370, 400].map((x) => (
                <line key={x} x1={x} x2={x} y1={y - 60} y2={y} className="stroke-sky-100 dark:stroke-sky-300/10" strokeWidth={2} />
              ))}
            </g>
          ))}
          <rect x={442} y={40} width={14} height={704} rx={4} fill={`url(#${ids.chromeX})`} />

          {/* Fridge column */}
          <path d={roundedPath({ x: 458, y: 40, w: 298, h: 704 }, 48, 12)} className={INSIDE} />
          <ellipse cx={607} cy={50} rx={100} ry={10} className="fill-amber-50 dark:fill-amber-100/10" />
          <GlassShelf x={458} y={161} w={298} ids={ids} />
          <GlassShelf x={458} y={285} w={298} ids={ids} />
          <GlassShelf x={458} y={409} w={298} ids={ids} />
          <Drawer box={BOX.meat} tint="fill-rose-100/70 stroke-rose-200 dark:fill-rose-300/10 dark:stroke-rose-300/20" />
          <Drawer box={BOX.veggies} tint="fill-green-100/80 stroke-green-200 dark:fill-green-300/10 dark:stroke-green-300/20" />
          <Drawer box={BOX.fruits} tint="fill-amber-100/80 stroke-amber-200 dark:fill-amber-300/10 dark:stroke-amber-300/20" />
          <text
            x={521}
            y={764}
            textAnchor="middle"
            className="fill-white/85 dark:fill-white/60"
            style={{ font: 'italic 700 20px Georgia, serif' }}
          >
            Kyokki
          </text>

          {/* Fridge door, swung open to the right */}
          <Hinge x={776} y={60} ids={ids} />
          <Hinge x={776} y={720} ids={ids} />
          <path d={roundedPath({ x: 794, y: 16, w: 146, h: 754 }, 40, 24)} className={RED} strokeWidth={2} />
          <path d={roundedPath({ x: 808, y: 34, w: 118, h: 718 }, 28, 14)} className={LINER} />
          <DoorBin box={{ x: 812, y: 96, w: 110, h: 80 }}>
            <Bottle x={824} base={164} w={18} h={50} className="fill-red-500 dark:fill-red-600" capClassName="fill-white dark:fill-slate-300" />
            <Bottle x={850} base={164} w={16} h={44} className="fill-yellow-400 dark:fill-yellow-500" capClassName="fill-red-600" />
            <Jar x={876} base={164} w={28} h={32} className="fill-amber-600/70 dark:fill-amber-700/60" />
          </DoorBin>
          <DoorBin box={{ x: 812, y: 214, w: 110, h: 62 }}>
            <Eggs x={832} base={266} count={5} gap={17} />
          </DoorBin>
          <DoorBin box={{ x: 812, y: 310, w: 110, h: 70 }}>
            <rect x={826} y={338} width={52} height={30} rx={4} className="fill-yellow-100 dark:fill-yellow-200/60" />
          </DoorBin>
          <DoorBin box={{ x: 812, y: 420, w: 110, h: 300 }}>
            <Bottle x={820} base={700} w={28} h={130} className="fill-emerald-400/70 dark:fill-emerald-500/40" capClassName="fill-emerald-700" />
            <Bottle x={854} base={700} w={28} h={112} className="fill-orange-300 dark:fill-orange-400/60" capClassName="fill-orange-600" />
            <Bottle x={888} base={700} w={28} h={140} className="fill-sky-200/90 dark:fill-sky-300/40" capClassName="fill-sky-600" />
          </DoorBin>
          <Handle box={{ x: 940, y: 250, w: 14, h: 240 }} ids={ids} />
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
              radius={
                area.id === 'freezer' || area.id === 'dairy'
                  ? 'rounded-t-[2.5rem] rounded-b-lg'
                  : 'rounded-xl'
              }
              center={area.id === 'freezer' || area.id === 'dairy'}
            />
          ))}
      </Canvas>
      <StaleShelf
        items={view.goingStale}
        expired={view.expired}
        onConsume={onConsume}
        onMore={onMore}
        onClearExpired={onClearExpired}
        orientation="column"
        className="border-2 border-red-200 bg-[#fff5f2] dark:border-red-950 dark:bg-[#2a2020]"
        accentClassName="text-red-700 dark:text-red-300"
      />
    </div>
  )
}

export default Rosso
