import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { starterCopyRefusal } from './starterCopy'

const refused = (status: number, body: object) => new ApiError(status, 'raw', null, body)

describe('starterCopyRefusal', () => {
  it('asks to confirm while the user has a starter copy', () => {
    expect(starterCopyRefusal(refused(409, { error: 'starter_exists' }))).toEqual({ kind: 'exists' })
  })
  it('says when to try again, or that there is no starter', () => {
    expect(starterCopyRefusal(refused(429, { error: 'starter_copy_too_soon', retry_after: 1500 }))).toEqual({ kind: 'message', text: 'One copy per hour: try again in 25 minutes.' })
    expect(starterCopyRefusal(refused(429, { error: 'starter_copy_too_soon' }))).toEqual({ kind: 'message', text: 'One copy per hour: try again later.' })
    expect(starterCopyRefusal(refused(404, { error: 'no_starter' }))).toEqual({ kind: 'message', text: 'There is no starter notebook to copy right now.' })
  })
  it("passes any other failure's sentence through", () => {
    expect(starterCopyRefusal(new ApiError(502, 'The service is not reachable'))).toEqual({ kind: 'message', text: 'The service is not reachable' })
  })
})
