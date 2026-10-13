import type { Source } from '../api/types'
import { madeFrom } from '../lib/sourceSelection'
import { tn } from '../i18n'

/** "from 3 sources" for a document made from a selection, the names as
 *  tooltip; nothing when it was made from all sources. */
export function MadeFrom({ ids, sources }: { ids: string[] | undefined; sources: Source[] | null }) {
  const m = madeFrom(ids, sources ?? [])
  if (!m) return null
  const title = [...m.names, ...(m.removed > 0 ? [tn('madeFrom.removed', m.removed)] : [])].join(', ')
  return (
    <span className="made-from" title={title}>
      {tn('madeFrom.n', m.n)}
    </span>
  )
}

