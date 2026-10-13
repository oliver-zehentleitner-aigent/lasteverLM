import { describe, expect, it } from 'vitest'
import { formatBytes } from './format'

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
