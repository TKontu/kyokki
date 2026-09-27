/**
 * The window beside the fridge (Q30): the sky for the time of day, and the moon in its phase.
 */

import { SKY_STATES, moonLitPath, moonPhase, moonIllumination, moonOpacity, skyAt } from '../sky'

const at = (hours: number, minutes = 0) => new Date(2026, 8, 27, hours, minutes)

describe('skyAt', () => {
  it.each([
    [0, 0, 'night'],
    [4, 59, 'night'],
    [5, 0, 'morning'],
    [8, 30, 'morning'],
    [9, 0, 'day'],
    [13, 0, 'day'],
    [17, 29, 'day'],
    [17, 30, 'dusk'],
    [21, 0, 'dusk'],
    [21, 30, 'night'],
    [23, 59, 'night'],
  ] as const)('at %i:%i the sky is %s', (hours, minutes, state) => {
    expect(skyAt(at(hours, minutes)).state).toBe(state)
  })

  it('has at least four states, each with its own colours', () => {
    expect(SKY_STATES.length).toBeGreaterThanOrEqual(4)
    const tops = SKY_STATES.map((state) => skyAt(at({ night: 1, morning: 7, day: 12, dusk: 19 }[state])).top)
    expect(new Set(tops).size).toBe(SKY_STATES.length)
  })

  it('reads the local clock, not UTC', () => {
    const local = new Date(2026, 0, 1, 12, 0)
    expect(skyAt(local).state).toBe('day')
  })

  it('moves the sun across the day: low in the morning, high at noon', () => {
    const morning = skyAt(at(6)).sun
    const noon = skyAt(at(13)).sun
    expect(morning).not.toBeNull()
    expect(noon).not.toBeNull()
    expect(noon!.height).toBeGreaterThan(morning!.height)
    expect(skyAt(at(1)).sun).toBeNull()
  })

  it('shows stars only at night', () => {
    expect(skyAt(at(1)).stars).toBe(true)
    expect(skyAt(at(12)).stars).toBe(false)
  })
})

describe('moonPhase', () => {
  // Published new and full moons (UTC); the approximation may be a day off.
  const DAY = 1 / 29.530588853

  const near = (phase: number, target: number) => {
    const distance = Math.min(Math.abs(phase - target), 1 - Math.abs(phase - target))
    expect(distance).toBeLessThanOrEqual(DAY)
  }

  it.each([
    ['2024-01-11T11:57:00Z'],
    ['2024-04-08T18:21:00Z'],
    ['2025-09-21T19:54:00Z'],
    ['2026-09-11T03:27:00Z'],
  ])('is new on %s', (iso) => {
    near(moonPhase(new Date(iso)), 0)
  })

  it.each([
    ['2024-01-25T17:54:00Z'],
    ['2024-10-17T11:26:00Z'],
    ['2025-09-07T18:09:00Z'],
    ['2026-09-26T16:49:00Z'],
  ])('is full on %s', (iso) => {
    near(moonPhase(new Date(iso)), 0.5)
  })

  it('always lies in [0, 1)', () => {
    for (const iso of ['1970-01-01', '1999-12-31', '2000-01-06T18:14:00Z', '2100-06-01']) {
      const phase = moonPhase(new Date(iso))
      expect(phase).toBeGreaterThanOrEqual(0)
      expect(phase).toBeLessThan(1)
    }
  })

  it('lights none of the moon when new and all of it when full', () => {
    expect(moonIllumination(0)).toBeCloseTo(0)
    expect(moonIllumination(0.5)).toBeCloseTo(1)
    expect(moonIllumination(0.25)).toBeCloseTo(0.5)
  })
})

describe('moonLitPath', () => {
  it('draws nothing lit at new moon', () => {
    expect(moonLitPath(0, 50, 50, 10)).toBeNull()
  })

  it('draws the full disc at full moon', () => {
    const path = moonLitPath(0.5, 50, 50, 10)
    expect(path).toContain('M50,40')
    expect(path).toContain('50,60')
  })

  it('lights the right side while waxing and the left while waning', () => {
    // The outer limb's sweep flag: 1 runs top -> right -> bottom, 0 top -> left -> bottom
    const sweepOf = (path: string) => path.split('A')[1].trim().split(/\s+/)[4]
    expect(sweepOf(moonLitPath(0.2, 50, 50, 10)!)).toBe('1')
    expect(sweepOf(moonLitPath(0.8, 50, 50, 10)!)).toBe('0')
  })

  it('bulges the terminator toward the lit side for a crescent and away for a gibbous', () => {
    const terminatorRx = (path: string) => Number(path.split('A')[2].trim().split(/[\s,]+/)[0])
    // A thin crescent's terminator is nearly the full radius; a half moon's is a straight line
    expect(terminatorRx(moonLitPath(0.05, 50, 50, 10)!)).toBeGreaterThan(8)
    expect(terminatorRx(moonLitPath(0.25, 50, 50, 10)!)).toBeCloseTo(0, 1)
  })
})

describe('moonOpacity', () => {
  it('is bright at night and faint by day', () => {
    expect(moonOpacity('night')).toBe(1)
    expect(moonOpacity('day')).toBeGreaterThan(0)
    expect(moonOpacity('day')).toBeLessThan(0.5)
  })
})
