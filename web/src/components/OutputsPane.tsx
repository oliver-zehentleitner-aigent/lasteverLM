import { useEffect, useState } from 'react'
import type { Output, OutputKind, Source } from '../api/types'
import { useOutputOptions } from '../hooks/useOutputOptions'
import { t } from '../i18n'
import { renamedTitle } from '../lib/conversations'
import { InlineRename } from './InlineRename'

/** rag's limit for an output title */
const OUTPUT_TITLE_MAX = 200
import { formatTime } from '../lib/format'
import { MadeFrom } from './MadeFrom'
import { shortId } from '../lib/outputId'
import { FILTER_FROM, SORTS, kindLabel, kindsPresent, optionsBrief, sortOutputs, whenLabel, type Sort } from '../lib/outputsList'

interface Props {
  outputs: Output[]
  selectedId: string | null
  onOpen: (id: string) => void
  onDelete: (o: Output) => void
  /** a double-click (or F2) on a row renames the output */
  onRename: (o: Output, title: string) => void
  /** the notebook's uploads, to name what a document was made from */
  sources: Source[] | null
}

/** Left column, under the output formats: the generated documents. Each row
 *  has the kind and the status in fixed slots, the title, and below it when
 *  it was made (relative within a day) with its language and voice, since a
 *  kind is often made again from the same sources. A sort control, and
 *  kind chips once the list is long. A click opens the tab; × deletes. */
export function OutputsPane({ outputs, selectedId, onOpen, onDelete, onRename, sources }: Props) {
  const [editing, setEditing] = useState<string | null>(null)
  const [sort, setSort] = useState<Sort>('newest')
  const [kind, setKind] = useState<OutputKind | 'all'>('all')
  const spec = useOutputOptions()
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000)
    return () => clearInterval(timer)
  }, [])

  const kinds = kindsPresent(outputs)
  // a filter on a kind that is gone (deleted) falls back to all
  const active = kind !== 'all' && kinds.includes(kind) ? kind : 'all'
  const shown = sortOutputs(active === 'all' ? outputs : outputs.filter((o) => o.kind === active), sort)
  const voiceLabel = (id: string) => spec?.audio.voices.find((v) => v.id === id)?.label ?? id

  return (
    <section className="pane outputs">
      <div className="outputs-head">
        <h2>{t('outputs.title')}</h2>
        {outputs.length > 1 && (
          <select className="outputs-sort" aria-label={t('outputs.sort')} value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            {SORTS.map((s) => (
              <option key={s} value={s}>
                {t(`sort.${s}`)}
              </option>
            ))}
          </select>
        )}
      </div>
      {outputs.length >= FILTER_FROM && kinds.length > 1 && (
        <div className="kind-chips" role="group" aria-label={t('outputs.filter')}>
          {(['all', ...kinds] as const).map((k) => (
            <button key={k} type="button" className={k === active ? 'preset active' : 'preset'} aria-pressed={k === active} onClick={() => setKind(k)}>
              {k === 'all' ? t('outputs.all') : kindLabel(k)}
            </button>
          ))}
        </div>
      )}
      <ul className="list out-list">
        {shown.map((o) => {
          const brief = optionsBrief(o, voiceLabel)
          return (
            <li key={o.id} id={`output-${o.id}`} className={o.id === selectedId ? 'selected' : ''}>
              {editing === o.id ? (
                <span className="out-row editing">
                  <span className="out-kind">
                    <span className="badge">{kindLabel(o.kind)}</span>
                  </span>
                  <InlineRename
                    className="item-edit out-title"
                    value={o.title || kindLabel(o.kind)}
                    label={t('outputs.renameLabel')}
                    maxLength={OUTPUT_TITLE_MAX}
                    onCancel={() => setEditing(null)}
                    onCommit={(draft) => {
                      setEditing(null)
                      const next = renamedTitle(draft, o.title)
                      if (next) onRename(o, next)
                    }}
                  />
                </span>
              ) : (
              <button
                type="button"
                className="out-row"
                onClick={() => onOpen(o.id)}
                // only a ready output can be renamed (rag answers 409 before: the worker would overwrite it)
                onDoubleClick={() => o.status === 'ready' && setEditing(o.id)}
                onKeyDown={(e) => {
                  if (e.key === 'F2' && o.status === 'ready') {
                    e.preventDefault()
                    setEditing(o.id)
                  }
                }}
                title={`${o.title || kindLabel(o.kind)} · ${t('outputId.label')} ${shortId(o.id)} · ${t('outputs.renameHint')}`}
              >
                <span className="out-kind">
                  <span className="badge">{kindLabel(o.kind)}</span>
                </span>
                <span className="out-title">{o.title || kindLabel(o.kind)}</span>
                <span className="out-status">
                  <span className={`badge ${o.status}`}>{t(`status.${o.status}`)}</span>
                </span>
                <span className="out-meta muted small">
                  <time dateTime={o.created_at} title={formatTime(o.created_at)}>
                    {whenLabel(o.created_at, now)}
                  </time>
                  {brief && ` · ${brief}`}
                  {o.options?.sources?.length ? (
                    <>
                      {' · '}
                      <MadeFrom ids={o.options.sources} sources={sources} />
                    </>
                  ) : null}
                </span>
              </button>
              )}
              <button type="button" className="icon" title={t('outputs.delete')} onClick={() => onDelete(o)}>
                ×
              </button>
            </li>
          )
        })}
        {outputs.length === 0 && <li className="muted small">{t('outputs.none')}</li>}
      </ul>
    </section>
  )
}
