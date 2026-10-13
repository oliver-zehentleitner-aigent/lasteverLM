import { describe, expect, it } from 'vitest'
import { isPdf, kindWithCapture, preferredCapture } from './capture'

describe('capture', () => {
  it('defaults to auto without a preference', () => {
    expect(preferredCapture(undefined)).toBe('auto')
    expect(preferredCapture({ ui_language: null, output_language: null, audio_voice: null, pdf_capture: null })).toBe('auto')
    expect(preferredCapture({ ui_language: null, output_language: null, audio_voice: null, pdf_capture: 'vision' })).toBe('vision')
  })

  it('recognises PDFs by type or name', () => {
    expect(isPdf({ name: 'a.PDF', type: '' })).toBe(true)
    expect(isPdf({ name: 'scan', type: 'application/pdf' })).toBe(true)
    expect(isPdf({ name: 'notes.txt', type: 'text/plain' })).toBe(false)
  })

  it('adds the mode to the kind label', () => {
    expect(kindWithCapture('PDF', 'vision')).toBe('PDF · vision')
    expect(kindWithCapture('Text', null)).toBe('Text')
  })
})
