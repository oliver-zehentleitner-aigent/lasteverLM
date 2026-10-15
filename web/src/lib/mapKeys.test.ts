import { describe, expect, it } from 'vitest'
import { mapAction, wheelAction } from './mapKeys'

describe('mapAction', () => {
  it('fits with 0 and zooms with plus and minus', () => {
    expect(mapAction('0')).toEqual({ kind: 'fit' })
    expect(mapAction('+')).toEqual({ kind: 'zoom', by: 1.25 })
    expect(mapAction('=')).toEqual({ kind: 'zoom', by: 1.25 })
    expect(mapAction('-')).toEqual({ kind: 'zoom', by: 0.8 })
  })

  it('leaves every other key alone', () => {
    expect(mapAction('a')).toBeNull()
    expect(mapAction('Escape')).toBeNull()
  })
})

describe('wheelAction', () => {
  const w = (o: Partial<{ deltaX: number; deltaY: number; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }>) => ({ deltaX: 0, deltaY: 0, shiftKey: false, ctrlKey: false, metaKey: false, ...o })
  it('scrolls, sideways with Shift, and leaves Ctrl (and a pinch) to the zoom', () => {
    expect(wheelAction(w({ deltaY: 40 }))).toEqual({ kind: 'pan', dx: 0, dy: 40 })
    expect(wheelAction(w({ deltaX: 12, deltaY: 30 }))).toEqual({ kind: 'pan', dx: 12, dy: 30 })
    expect(wheelAction(w({ deltaY: 40, shiftKey: true }))).toEqual({ kind: 'pan', dx: 40, dy: 0 })
    expect(wheelAction(w({ deltaX: 25, deltaY: 0, shiftKey: true }))).toEqual({ kind: 'pan', dx: 25, dy: 0 })
    expect(wheelAction(w({ deltaY: -3, ctrlKey: true }))).toEqual({ kind: 'zoom-native' })
  })
  it('zooms a step with Cmd', () => {
    expect(wheelAction(w({ deltaY: -40, metaKey: true }))).toEqual({ kind: 'zoom', by: 1.1 })
    expect(wheelAction(w({ deltaY: 40, metaKey: true }))).toEqual({ kind: 'zoom', by: 1 / 1.1 })
  })
})
