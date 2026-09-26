'use client'

/**
 * Crema (Q17-M): a cream retro fridge with the freezer on top and both doors swung open, so
 * the door bins show; a wooden pantry cupboard on its left and the going-stale shelf as a
 * strip across the top.
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
const H = 560

const BOX: Record<AreaId, Box> = {
  meat: { x: 318, y: 374, w: 364, h: 56 },
  veggies: { x: 318, y: 434, w: 180, h: 80 },
  fruits: { x: 502, y: 434, w: 180, h: 80 },
  dairy: { x: 312, y: 172, w: 376, h: 64 },
  bread: { x: 312, y: 240, w: 376, h: 62 },
  ready_meals: { x: 312, y: 306, w: 376, h: 62 },
  drinks: { x: 736, y: 372, w: 122, h: 146 },
  pantry: { x: 36, y: 150, w: 198, h: 370 },
  freezer: { x: 312, y: 36, w: 376, h: 118 },
  other: { x: 893, y: 430, w: 100, h: 106 },
}

const LAYOUT: Partial<Record<AreaId, 'column'>> = {
  veggies: 'column',
  fruits: 'column',
  drinks: 'column',
  pantry: 'column',
  other: 'column',
}

const CREAM = 'fill-[#f2e7cd] stroke-[#dccba2] dark:fill-[#d3c39c] dark:stroke-[#a89770]'
const LINER = 'fill-[#fbf7ee] dark:fill-[#34363b]'
const INSIDE = 'fill-[#fefdf9] dark:fill-[#2a2c30]'
const ICE = 'fill-[#e3f1f8] dark:fill-[#1c2e39]'
const WOOD = 'fill-[#c9a27a] dark:fill-[#6d533e]'
const WOOD_DARK = 'fill-[#a88058] dark:fill-[#54402f]'
const WOOD_INSIDE = 'fill-[#f5e9d6] dark:fill-[#3a3029]'

export function Crema({ items, onConsume, onMore, onClearExpired }: FridgeMockProps) {
  const { view, byId, hasOther } = useFridge(items)
  const ids = useSvgIds('chromeX', 'chromeY', 'gloss', 'glass')

  return (
    <div data-testid="fridge-mock-crema" className="flex h-full min-h-0 flex-col gap-3">
      <StaleShelf
        items={view.goingStale}
        expired={view.expired}
        onConsume={onConsume}
        onMore={onMore}
        onClearExpired={onClearExpired}
        orientation="row"
        className="border-2 border-[#e6d5ad] bg-[#fbf4e2] shadow-inner dark:border-[#4b4432] dark:bg-[#2b2922]"
        accentClassName="text-[#9b3b2f] dark:text-[#f0b8a8]"
      />
      <Canvas width={W} height={H}>
        <Drawing width={W} height={H}>
          <Defs ids={ids} />
          {/* Floor */}
          <rect x={0} y={538} width={W} height={22} rx={4} className="fill-[#e8e0d2] dark:fill-[#25262b]" />
          <ellipse cx={500} cy={540} rx={250} ry={7} className="fill-black/15 dark:fill-black/40" />

          {/* Pantry cupboard */}
          <rect x={12} y={104} width={246} height={20} rx={6} className={WOOD_DARK} />
          <rect x={20} y={120} width={230} height={420} rx={10} className={WOOD} />
          <rect x={36} y={150} width={198} height={370} rx={6} className={WOOD_INSIDE} />
          {[242, 334, 426].map((y) => (
            <rect key={y} x={36} y={y} width={198} height={8} className={WOOD_DARK} />
          ))}
          <Jar x={186} base={242} w={26} h={34} className="fill-amber-300/80 dark:fill-amber-500/50" lidClassName="fill-rose-500 dark:fill-rose-700" />
          <Jar x={156} base={242} w={22} h={26} className="fill-orange-200/90 dark:fill-orange-400/40" />
          <Jar x={192} base={334} w={24} h={30} className="fill-slate-300 dark:fill-slate-500" lidClassName="fill-slate-400 dark:fill-slate-600" />
          <Bottle x={196} base={426} w={18} h={48} className="fill-lime-700/60 dark:fill-lime-600/40" />
          <rect x={150} y={480} width={62} height={40} rx={8} className="fill-[#e7d4b0] dark:fill-[#5c4a38]" />
          <rect x={20} y={520} width={230} height={18} rx={4} className={WOOD_DARK} />

          {/* Fridge body, cavities and legs */}
          <rect x={322} y={528} width={20} height={16} rx={4} fill={`url(#${ids.chromeX})`} />
          <rect x={658} y={528} width={20} height={16} rx={4} fill={`url(#${ids.chromeX})`} />
          <path d={roundedPath({ x: 290, y: 14, w: 420, h: 522 }, 72, 26)} className={CREAM} strokeWidth={2} />
          <path d={roundedPath({ x: 290, y: 14, w: 420, h: 522 }, 72, 26)} fill={`url(#${ids.gloss})`} />
          <path d={roundedPath(BOX.freezer, 54, 10)} className={ICE} />
          <line x1={330} x2={670} y1={104} y2={104} className="stroke-sky-200 dark:stroke-sky-300/20" strokeWidth={3} />
          {[380, 440, 500, 560, 620].map((x) => (
            <line key={x} x1={x} x2={x - 10} y1={104} y2={150} className="stroke-sky-100 dark:stroke-sky-300/10" strokeWidth={2} />
          ))}
          <rect x={300} y={160} width={400} height={5} rx={2} fill={`url(#${ids.chromeY})`} />
          <path d={roundedPath({ x: 312, y: 172, w: 376, h: 346 }, 12, 30)} className={INSIDE} />
          <ellipse cx={500} cy={180} rx={120} ry={10} className="fill-amber-50 dark:fill-amber-100/10" />
          <GlassShelf x={312} y={238} w={376} ids={ids} />
          <GlassShelf x={312} y={304} w={376} ids={ids} />
          <GlassShelf x={312} y={370} w={376} ids={ids} />
          <Drawer box={BOX.meat} tint="fill-rose-100/70 stroke-rose-200 dark:fill-rose-300/10 dark:stroke-rose-300/20" />
          <Drawer box={BOX.veggies} tint="fill-green-100/80 stroke-green-200 dark:fill-green-300/10 dark:stroke-green-300/20" />
          <Drawer box={BOX.fruits} tint="fill-amber-100/80 stroke-amber-200 dark:fill-amber-300/10 dark:stroke-amber-300/20" />
          {[470, 490, 510, 530].map((x) => (
            <rect key={x} x={x} y={524} width={12} height={4} rx={2} className="fill-black/10 dark:fill-black/30" />
          ))}

          {/* Doors, swung open to the right */}
          <Hinge x={704} y={40} ids={ids} />
          <Hinge x={704} y={180} ids={ids} />
          <Hinge x={704} y={500} ids={ids} />
          <path d={roundedPath({ x: 722, y: 14, w: 150, h: 140 }, 40, 8)} className={CREAM} strokeWidth={2} />
          <path d={roundedPath({ x: 736, y: 28, w: 122, h: 112 }, 28, 6)} className={LINER} />
          <text
            x={797}
            y={64}
            textAnchor="middle"
            className="fill-[#b9a57a] dark:fill-[#8f8a80]"
            style={{ font: 'italic 700 22px Georgia, serif' }}
          >
            Kyokki
          </text>
          <DoorBin box={{ x: 740, y: 84, w: 114, h: 46 }}>
            <rect x={754} y={98} width={34} height={22} rx={3} className="fill-sky-200/80 dark:fill-sky-300/30" />
            <rect x={796} y={98} width={34} height={22} rx={3} className="fill-sky-200/80 dark:fill-sky-300/30" />
          </DoorBin>
          <Handle box={{ x: 872, y: 46, w: 12, h: 76 }} ids={ids} />

          <path d={roundedPath({ x: 722, y: 162, w: 150, h: 374 }, 8, 26)} className={CREAM} strokeWidth={2} />
          <path d={roundedPath({ x: 736, y: 176, w: 122, h: 346 }, 6, 18)} className={LINER} />
          <DoorBin box={{ x: 740, y: 196, w: 114, h: 66 }}>
            <Bottle x={754} base={250} w={18} h={46} className="fill-red-500 dark:fill-red-600" capClassName="fill-white dark:fill-slate-300" />
            <Bottle x={780} base={250} w={16} h={40} className="fill-yellow-400 dark:fill-yellow-500" capClassName="fill-red-600" />
            <Jar x={806} base={250} w={26} h={30} className="fill-amber-600/70 dark:fill-amber-700/60" />
          </DoorBin>
          <DoorBin box={{ x: 740, y: 284, w: 114, h: 60 }}>
            <Eggs x={760} base={334} count={5} gap={18} />
          </DoorBin>
          <DoorBin box={{ x: 740, y: 372, w: 114, h: 146 }}>
            <Bottle x={752} base={500} w={26} h={82} className="fill-emerald-400/70 dark:fill-emerald-500/40" capClassName="fill-emerald-700" />
            <Bottle x={784} base={500} w={26} h={74} className="fill-orange-300 dark:fill-orange-400/60" capClassName="fill-orange-600" />
            <Bottle x={816} base={500} w={26} h={88} className="fill-sky-200/90 dark:fill-sky-300/40" capClassName="fill-sky-600" />
          </DoorBin>
          <Handle box={{ x: 872, y: 206, w: 12, h: 150 }} ids={ids} />

          {hasOther && <Basket box={{ x: 897, y: 474, w: 92, h: 62 }} />}
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
              radius={area.id === 'freezer' ? 'rounded-t-[3rem] rounded-b-lg' : 'rounded-xl'}
              center={area.id === 'freezer'}
            />
          ))}
      </Canvas>
    </div>
  )
}

export default Crema
