/** What the admin output search sends: the typed ID without hyphens and
 *  spaces, lowercase, as rag matches it (against the dashless hex); null
 *  until it is 6 to 32 hex characters, which rag requires. */
export function idPrefix(input: string): string | null {
  const p = input.replace(/[\s-]/g, '').toLowerCase()
  return /^[0-9a-f]{6,32}$/.test(p) ? p : null
}
