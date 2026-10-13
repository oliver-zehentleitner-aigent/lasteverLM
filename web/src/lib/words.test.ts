import { describe, expect, it } from 'vitest'
import { words } from './words'

describe('words', () => {
  it('keeps letters and digits of three or more, lower-cased', () => {
    expect([...words('The Kubernetes API, v2 and 2026: ok?')]).toEqual(['the', 'kubernetes', 'api', 'and', '2026'])
  })

  it('handles umlauts and other scripts', () => {
    expect(words('Größe Übersicht').has('größe')).toBe(true)
    expect(words('Größe Übersicht').has('übersicht')).toBe(true)
  })
})
