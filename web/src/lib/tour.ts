import type { User } from '../api/types'

/** The introduction's steps: what each points at (a selector in the
 *  notebook view) and its text keys. The last one says "redeem a voucher
 *  first" without credit. */
export const TOUR_STEPS = [
  { target: '.pane.sources', key: 'sources' },
  { target: '.tiles .tile-grid', key: 'format' },
  { target: '.tiles .create-row', key: 'create' },
] as const

const localKey = (userId: string) => `lasteverlm.tourDone.${userId}`

/** Whether the introduction is done for this user: the account's
 *  `tour_done`, or this browser's note where the account cannot keep it
 *  (the shared demo user, an account service before the preference).
 *  Pure apart from the storage it is given, so it is tested. */
export function tourDone(me: Pick<User, 'id' | 'preferences'> | null | undefined, storage: Pick<Storage, 'getItem'> | undefined): boolean {
  if (!me) return true
  if (me.preferences?.tour_done === true) return true
  try {
    return storage?.getItem(localKey(me.id)) === '1'
  } catch {
    return false
  }
}

/** This browser's note, set alongside the preference and cleared to show it again. */
export function noteTourDone(storage: Pick<Storage, 'setItem' | 'removeItem'> | undefined, userId: string, done: boolean): void {
  try {
    if (done) storage?.setItem(localKey(userId), '1')
    else storage?.removeItem(localKey(userId))
  } catch {
    // no storage: the preference alone decides
  }
}
