/**
 * The window beside the fridge (Q30): what the sky looks like at a given local time, and the
 * moon's phase on a given date. Pure, so the drawing can be recomputed on a timer and a test
 * can pin any hour.
 */

export type SkyState = 'morning' | 'day' | 'dusk' | 'night'

export const SKY_STATES: SkyState[] = ['morning', 'day', 'dusk', 'night']

export interface Sky {
  state: SkyState
  /** The gradient's colours, top of the pane to the bottom. */
  top: string
  bottom: string
  /**
   * Where the sun is, as shares of the pane: `x` from left to right as the day goes on,
   * `height` from the horizon (0) to the top (1). `null` at night.
   */
  sun: { x: number; height: number } | null
  stars: boolean
}

// Fixed hours, local time. The kitchen is in Finland, where the real sunrise wanders by hours
// through the year; the window is decoration, so a steady day reads better than an almanac.
const MORNING = 5
const DAY = 9
const DUSK = 17.5
const NIGHT = 21.5

const COLOURS: Record<SkyState, { top: string; bottom: string }> = {
  morning: { top: '#9fc9ec', bottom: '#ffd9b0' },
  day: { top: '#6fb7ea', bottom: '#d4ecfb' },
  dusk: { top: '#3d4b86', bottom: '#f39a6b' },
  night: { top: '#0f1a3a', bottom: '#2a3563' },
}

/** The sky at `date`'s local time. */
export function skyAt(date: Date): Sky {
  const hours = date.getHours() + date.getMinutes() / 60
  const state: SkyState =
    hours < MORNING || hours >= NIGHT
      ? 'night'
      : hours < DAY
        ? 'morning'
        : hours < DUSK
          ? 'day'
          : 'dusk'
  let sun: Sky['sun'] = null
  if (state !== 'night') {
    const t = (hours - MORNING) / (NIGHT - MORNING)
    sun = { x: t, height: Math.sin(Math.PI * t) }
  }
  return { state, ...COLOURS[state], sun, stars: state === 'night' }
}

/** How strongly the moon shows: bright at night, faint by day. */
export function moonOpacity(state: SkyState): number {
  return { night: 1, dusk: 0.6, morning: 0.35, day: 0.25 }[state]
}

/** The mean synodic month, in days. */
const SYNODIC = 29.530588853
/** A known new moon: 2000-01-06 18:14 UTC. */
const NEW_MOON = Date.UTC(2000, 0, 6, 18, 14)
const DAY_MS = 86_400_000

/**
 * The moon's phase at `date`: 0 new, 0.25 first quarter, 0.5 full, 0.75 last quarter, in
 * [0, 1). The mean synodic month from a known new moon, so within about a day of the real one.
 */
export function moonPhase(date: Date): number {
  const days = (date.getTime() - NEW_MOON) / DAY_MS
  const phase = (days / SYNODIC) % 1
  return phase < 0 ? phase + 1 : phase
}

/** The share of the disc that is lit at `phase`. */
export function moonIllumination(phase: number): number {
  return (1 - Math.cos(2 * Math.PI * phase)) / 2
}

const round = (value: number) => Math.round(value * 100) / 100

/**
 * The lit part of a moon at `phase`, centred on (cx, cy) with radius r, as an SVG path; `null`
 * at new moon, when nothing is lit. As seen from the northern hemisphere: the right side is lit
 * while waxing, the left while waning. The path runs along the lit limb from top to bottom,
 * then back up the terminator - an ellipse whose width shrinks to nothing at the quarters.
 */
export function moonLitPath(phase: number, cx: number, cy: number, r: number): string | null {
  if (moonIllumination(phase) < 0.02) return null
  const top = `${round(cx)},${round(cy - r)}`
  const bottom = `${round(cx)},${round(cy + r)}`
  const waxing = phase < 0.5
  const terminator = round(r * Math.abs(Math.cos(2 * Math.PI * phase)))
  // Sweep 1 runs clockwise on screen: top -> right -> bottom, or bottom -> left -> top
  const limbSweep = waxing ? 1 : 0
  const crescent = waxing ? phase < 0.25 : phase > 0.75
  // A crescent's terminator bulges toward the lit limb, a gibbous one's away from it
  const terminatorSweep = crescent ? 1 - limbSweep : limbSweep
  return [
    `M${top}`,
    `A${round(r)} ${round(r)} 0 0 ${limbSweep} ${bottom}`,
    `A${terminator} ${round(r)} 0 0 ${terminatorSweep} ${top}`,
    'Z',
  ].join(' ')
}
