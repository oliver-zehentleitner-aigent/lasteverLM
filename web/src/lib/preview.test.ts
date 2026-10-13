import { describe, expect, it } from 'vitest'
import { previewPosition } from './preview'

const vp = { width: 1000, height: 800 }
const size = { width: 320, height: 240 }

describe('previewPosition', () => {
  it('goes right of the anchor when it fits, centred on it', () => {
    expect(previewPosition({ left: 100, right: 132, top: 300, bottom: 332 }, vp, size)).toEqual({ left: 140, top: 196 })
  })

  it('goes left when the right side is too narrow', () => {
    expect(previewPosition({ left: 800, right: 832, top: 300, bottom: 332 }, vp, size)).toEqual({ left: 472, top: 196 })
  })

  it('stays inside the viewport near the edges and on narrow screens', () => {
    expect(previewPosition({ left: 100, right: 132, top: 10, bottom: 42 }, vp, size).top).toBe(8)
    expect(previewPosition({ left: 100, right: 132, top: 780, bottom: 796 }, vp, size).top).toBe(552)
    expect(previewPosition({ left: 50, right: 82, top: 300, bottom: 332 }, { width: 360, height: 640 }, size).left).toBe(32)
  })
})
