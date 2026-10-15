import { describe, expect, it } from 'vitest'
import { readByLine } from './readBy'

describe('readByLine', () => {
  it('names the model that described an image, read a PDF page or transcribed audio', () => {
    expect(readByLine('image', { vision: 'qwen-vl', stt: null })).toBe('Described by qwen-vl, not a verbatim transcript')
    expect(readByLine('pdf', { vision: 'qwen-vl', stt: null }, true)).toBe('Page read by qwen-vl')
    expect(readByLine('audio', { vision: null, stt: 'whisper' })).toBe('Transcribed by whisper')
  })
  it('says nothing for a PDF page read from its text layer, or where nothing was recorded', () => {
    expect(readByLine('pdf', { vision: 'qwen-vl', stt: null }, false)).toBeNull()
    expect(readByLine('pdf', { vision: 'qwen-vl', stt: null })).toBeNull()
    expect(readByLine('image', null)).toBeNull()
    expect(readByLine('text', { vision: 'x', stt: 'y' })).toBeNull()
  })
})
