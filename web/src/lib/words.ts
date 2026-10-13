/** The words of a text that carry meaning for matching: letters or digits,
 *  three or more, lower-cased; shared by the provenance mark and the
 *  passage search in generated documents. */
export function words(s: string): Set<string> {
  return new Set(s.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? [])
}
