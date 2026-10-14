import { describe, expect, it } from 'vitest'
import { SIGN_IN_CODE_LENGTH, checkCode, cleanCode } from './signInCode'

const code = 'aB3_-'.repeat(8) + 'xyz' // 43

describe('sign-in code', () => {
  it('accepts 43 URL-safe characters', () => {
    expect(code).toHaveLength(SIGN_IN_CODE_LENGTH)
    expect(checkCode(code)).toBe('ok')
  })

  it('names what is wrong', () => {
    expect(checkCode('')).toBe('empty')
    expect(checkCode(code.slice(1))).toBe('length')
    expect(checkCode(code + 'a')).toBe('length')
    expect(checkCode(code.slice(1) + '=')).toBe('chars')
    expect(checkCode(code.slice(1) + '+')).toBe('chars')
  })

  it('drops the whitespace a mail client adds, wherever it is', () => {
    expect(cleanCode(`  ${code.slice(0, 20)}\n${code.slice(20)} \t`)).toBe(code)
  })
})
