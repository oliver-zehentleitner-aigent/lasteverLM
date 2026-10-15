import { describe, expect, it } from 'vitest'
import { formatBytes, formatShortTime } from './format'

describe('formatBytes', () => {
  it('keeps bytes whole and steps up by 1024 with one decimal', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(5 * 1024 ** 3)).toBe('5.0 GB')
  })

  it('stops at TB', () => {
    expect(formatBytes(3 * 1024 ** 5)).toBe('3072.0 TB')
  })
})

describe('formatShortTime', () => {
  it('is day, month and time, the year only when it is another', () => {
    const now = new Date('2026-10-15T12:00:00')
    const same = formatShortTime('2026-10-15T20:53:00', now)
    expect(same).toMatch(/20:53|8:53/)
    expect(same).not.toMatch(/2026/)
    expect(formatShortTime('2025-03-02T09:05:00', now)).toMatch(/2025/)
    expect(formatShortTime(null, now)).toBe('never')
  })
})
