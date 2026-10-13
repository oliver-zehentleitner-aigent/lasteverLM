/** Version and commit as people read them. Core reports "unknown" for an
 *  unset value; that and null count as missing. */
export function known(v: string | null | undefined): string | null {
  return v && v !== 'unknown' ? v : null
}

/** The first 7 characters of a commit, as git shows it. */
export function shortCommit(c: string | null | undefined): string | null {
  const k = known(c)
  return k ? k.slice(0, 7) : null
}

/** "lasteverLM 0.6.1 · 5e320ae", or with whatever part is known; null when
 *  neither is. */
export function versionLine(version: string | null | undefined, commit: string | null | undefined): string | null {
  const v = known(version)
  const c = shortCommit(commit)
  if (!v && !c) return null
  return ['lasteverLM', v, c && `· ${c}`].filter(Boolean).join(' ')
}
