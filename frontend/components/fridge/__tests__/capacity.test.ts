/**
 * How many dots an area's region holds before it shows a "more" marker instead (Q17-B).
 * The overlay is sized in the drawing's own units, so the answer depends on the box alone.
 */

import { DOT, DOT_PITCH, HEADER, PAD, dotCapacity, dotSlot, fitDots } from '../capacity'

describe('dotCapacity', () => {
  it('fills the box below the label with rows of dots', () => {
    const w = PAD * 2 + DOT_PITCH * 5
    const h = PAD * 2 + HEADER + DOT_PITCH * 3
    expect(dotCapacity({ x: 0, y: 0, w, h })).toBe(15)
  })

  it('holds nothing when the box is too small for a row', () => {
    expect(dotCapacity({ x: 0, y: 0, w: 200, h: PAD * 2 + HEADER })).toBe(0)
  })
})

describe('fitDots', () => {
  const list = ['a', 'b', 'c', 'd', 'e']

  it('shows them all when they fit', () => {
    expect(fitDots(list, 5)).toEqual({ shown: list, more: false })
  })

  it('gives the last slot to the marker when they do not', () => {
    expect(fitDots(list, 4)).toEqual({ shown: ['a', 'b', 'c'], more: true })
  })

  it('still shows the marker in a box with room for one', () => {
    expect(fitDots(list, 1)).toEqual({ shown: [], more: true })
  })

  it('shows the marker alone when there is no room at all', () => {
    expect(fitDots(list, 0)).toEqual({ shown: [], more: true })
  })
})

describe('dotSlot', () => {
  const box = { x: 0, y: 0, w: PAD * 2 + DOT_PITCH * 5, h: PAD * 2 + HEADER + DOT_PITCH * 3 }

  it('fills rows left to right below the label', () => {
    expect(dotSlot(0, box)).toEqual({ left: PAD, top: PAD + HEADER })
    expect(dotSlot(4, box)).toEqual({ left: PAD + DOT_PITCH * 4, top: PAD + HEADER })
    expect(dotSlot(5, box)).toEqual({ left: PAD, top: PAD + HEADER + DOT_PITCH })
  })

  it('keeps the last slot inside the box', () => {
    const last = dotSlot(dotCapacity(box) - 1, box)
    expect(last.left + DOT).toBeLessThanOrEqual(box.w)
    expect(last.top + DOT).toBeLessThanOrEqual(box.h)
  })
})
