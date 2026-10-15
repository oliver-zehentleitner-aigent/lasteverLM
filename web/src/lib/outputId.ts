/** An output's short ID, as people quote it: the first 8 lowercase hex
 *  characters of its UUID, core's `short_id` convention, so the web, the
 *  logs and the admin search name an output the same way. */
export function shortId(id: string): string {
  return id.replace(/-/g, '').slice(0, 8).toLowerCase()
}
