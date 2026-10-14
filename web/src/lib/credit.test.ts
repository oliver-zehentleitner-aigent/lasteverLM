import { describe, expect, it } from 'vitest'
import type { CreditEntry } from '../api/types'
import { creditLine } from './credit'

const charge = (over: Partial<CreditEntry>): CreditEntry => ({ at: '2026-10-14T10:00:00Z', type: 'charge', amount_cents: -3, action: null, label_key: null, notebook: null, output: null, source: null, ...over })

describe('creditLine', () => {
  it('names an output with its notebook and links to both', () => {
    expect(creditLine(charge({ label_key: 'output:report', notebook: { id: 'n1', title: 'test1' }, output: { id: 'o1', title: null } }))).toEqual({
      text: 'Report in notebook test1',
      open: { notebookId: 'n1' },
    })
    expect(creditLine(charge({ label_key: 'output:report', notebook: { id: 'n1', title: 'test1' }, output: { id: 'o1', title: 'Fog' } })).open).toEqual({ notebookId: 'n1', outputId: 'o1' })
  })

  it('names a processed source, also once it is gone', () => {
    expect(creditLine(charge({ label_key: 'source:pdf', source: { id: 's1', title: 'linux_vi.pdf' }, notebook: { id: 'n1', title: 'x' } })).text).toBe('Source linux_vi.pdf processed')
    expect(creditLine(charge({ label_key: 'source:pdf', source: { id: 's1', title: null } })).text).toBe('Source (deleted) processed')
  })

  it('names a question by its notebook, and a deleted notebook links nowhere', () => {
    expect(creditLine(charge({ label_key: 'chat_answer', notebook: { id: 'n1', title: null } }))).toEqual({ text: 'Question to your sources in notebook (deleted)', open: null })
  })

  it('names vouchers and grants', () => {
    expect(creditLine(charge({ type: 'voucher', amount_cents: 500 })).text).toBe('Voucher redeemed')
    expect(creditLine(charge({ type: 'grant', amount_cents: 500 })).text).toBe('Credit granted')
  })
})
