import type { User } from '../api/types'

/** The introduction's steps: what each outlines (selectors in the
 *  notebook view, every one found is outlined) and its text keys. The
 *  credit step opens the profile menu and the voucher dialog for as long
 *  as it is shown (`TOUR_CREDIT`), and outlines the menu's "Redeem a
 *  voucher" and the dialog together. An area not on screen (a phone's
 *  stacked layout hides some) leaves the card in the middle. */
export const TOUR_STEPS = [
  { key: 'notebook', targets: ['.notebooks form'] },
  { key: 'sources', targets: ['.pane.sources'] },
  { key: 'format', targets: ['.tiles'] },
  { key: 'outputs', targets: ['.pane.outputs'] },
  { key: 'viewer', targets: ['.pane.viewer'] },
  { key: 'chat', targets: ['.pane.chat'] },
  { key: 'credit', targets: ['.profile-menu [data-item="redeem"]', '.voucher-dialog'], credit: true },
] as const satisfies readonly { key: string; targets: readonly string[]; credit?: boolean }[]

/** The credit step's signal: true while it is shown (the header opens its
 *  menu, the app the voucher dialog), false when it is left. */
export const tourEvents = new EventTarget()
export const TOUR_CREDIT = 'tour-credit'

export function signalCreditStep(on: boolean): void {
  tourEvents.dispatchEvent(new CustomEvent<boolean>(TOUR_CREDIT, { detail: on }))
}

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
