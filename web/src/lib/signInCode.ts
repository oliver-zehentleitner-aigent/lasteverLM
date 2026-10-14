/** The code in the sign-in mail is the magic link's token as text
 *  (secrets.token_urlsafe(32) in the account service): 43 characters of
 *  the URL-safe base64 alphabet. Checked before it is sent, so a code cut
 *  short by a copy is named as such instead of costing a round trip. */
export const SIGN_IN_CODE_LENGTH = 43

const ALPHABET = /^[A-Za-z0-9_-]*$/

/** What was pasted, without the whitespace a mail client adds around it. */
export function cleanCode(raw: string): string {
  return raw.replace(/\s+/g, '')
}

export type CodeCheck = 'empty' | 'chars' | 'length' | 'ok'

export function checkCode(code: string): CodeCheck {
  if (!code) return 'empty'
  if (!ALPHABET.test(code)) return 'chars'
  return code.length === SIGN_IN_CODE_LENGTH ? 'ok' : 'length'
}
