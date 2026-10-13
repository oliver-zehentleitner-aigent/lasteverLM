import { describe, expect, it } from 'vitest'
import {
  DEFAULT_VIEWER_RATIO,
  MAX_VIEWER_RATIO,
  MIN_VIEWER_RATIO,
  activePreset,
  clampRatio,
  clampWidth,
  presetRatio,
  ratioFromPointer,
  readRatio,
  readWidth,
  writeRatio,
  writeWidth,
} from './layout'

function memory() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
  }
}

describe('viewer ratio', () => {
  it('clamps to the allowed range and falls back on garbage', () => {
    expect(clampRatio(0.05)).toBe(MIN_VIEWER_RATIO)
    expect(clampRatio(0.99)).toBe(MAX_VIEWER_RATIO)
    expect(clampRatio(Number.NaN)).toBe(DEFAULT_VIEWER_RATIO)
  })

  it('turns a pointer position into a ratio of the column', () => {
    expect(ratioFromPointer(300, 100, 400)).toBe(0.5)
    expect(ratioFromPointer(100, 100, 0)).toBe(DEFAULT_VIEWER_RATIO)
  })

  it('remembers, resets and survives a storage that throws', () => {
    const s = memory()
    expect(readRatio(s)).toBe(DEFAULT_VIEWER_RATIO)
    writeRatio(s, 0.7)
    expect(readRatio(s)).toBe(0.7)
    writeRatio(s, null)
    expect(readRatio(s)).toBe(DEFAULT_VIEWER_RATIO)
    const broken = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
    }
    expect(readRatio(broken)).toBe(DEFAULT_VIEWER_RATIO)
    expect(() => writeRatio(broken, 0.6)).not.toThrow()
  })
})

describe('chat presets', () => {
  it('map the chat share to a viewer ratio inside the bounds', () => {
    expect(presetRatio(0.15)).toBeCloseTo(0.85)
    expect(presetRatio(0.3)).toBeCloseTo(0.7)
    expect(presetRatio(0.45)).toBeCloseTo(0.55)
  })

  it('highlight the preset the ratio matches, none after a drag', () => {
    expect(activePreset(presetRatio(0.3))).toBe('2x')
    expect(activePreset(0.62)).toBeNull()
    expect(activePreset(DEFAULT_VIEWER_RATIO)).toBeNull()
  })
})

describe('column widths', () => {
  it('clamps, remembers and resets to the default', () => {
    expect(clampWidth(100, 160, 420)).toBe(160)
    const s = memory()
    expect(readWidth(s, 'w', 160, 420)).toBeNull()
    writeWidth(s, 'w', 300.4)
    expect(readWidth(s, 'w', 160, 420)).toBe(300)
    writeWidth(s, 'w', 999)
    expect(readWidth(s, 'w', 160, 420)).toBe(420)
    writeWidth(s, 'w', null)
    expect(readWidth(s, 'w', 160, 420)).toBeNull()
  })
})
