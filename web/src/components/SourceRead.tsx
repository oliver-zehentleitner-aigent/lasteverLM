import { useEffect, useRef, useState } from 'react'
import { ingest } from '../api/ingest'
import type { SourceChunks } from '../api/types'
import { useAsync } from '../hooks/useAsync'
import { t } from '../i18n'
import { flash } from '../lib/locate'
import { CHUNK_PAGE, chunkPageOffset } from '../lib/viewerTabs'

/** A source as the system read it: the extracted text chunk by chunk,
 *  each with its number (and page, for a PDF), 50 at a time. Opened from a
 *  citation, it loads the page the cited chunk is on, marks that chunk and
 *  scrolls it into view. The caller remounts it for every open, so a new
 *  citation starts on its own page. */
export function SourceRead({ sourceId, chunkId, chunkIndex }: { sourceId: string; chunkId: string | null; chunkIndex: number | null }) {
  const [offset, setOffset] = useState(() => chunkPageOffset(chunkIndex))
  const [data, setData] = useState<SourceChunks | null>(null)
  const { busy, error, run } = useAsync()
  const list = useRef<HTMLOListElement>(null)

  useEffect(() => {
    void run(async () => setData(await ingest.sourceChunks(sourceId, offset, CHUNK_PAGE)))
  }, [run, sourceId, offset])

  useEffect(() => {
    if (!chunkId || !data) return
    const el = list.current?.querySelector<HTMLElement>(`[data-chunk-id="${CSS.escape(chunkId)}"]`)
    if (el) flash(el)
  }, [chunkId, data])

  if (error) return <p className="error">{error}</p>
  if (!data) return <p className="muted">{busy ? t('common.loading') : ''}</p>
  if (data.chunk_count === 0) return <p className="muted">{t('srcView.noChunks')}</p>
  const last = Math.min(data.offset + data.chunks.length, data.chunk_count)
  const pager = data.chunk_count > CHUNK_PAGE && (
    <p className="chunk-pager muted small no-print">
      <button type="button" className="link" disabled={busy || data.offset === 0} onClick={() => setOffset(Math.max(0, data.offset - CHUNK_PAGE))}>
        {t('srcView.prev')}
      </button>
      {t('srcView.range', { from: data.offset + 1, to: last, n: data.chunk_count })}
      <button type="button" className="link" disabled={busy || last >= data.chunk_count} onClick={() => setOffset(data.offset + CHUNK_PAGE)}>
        {t('srcView.next')}
      </button>
    </p>
  )
  return (
    <div className="source-read">
      <p className="muted small">{t('srcView.readIntro', { n: data.chunk_count })}</p>
      {pager}
      <ol className="chunks" ref={list}>
        {data.chunks.map((c) => (
          <li key={c.chunk_id} data-chunk-id={c.chunk_id} className={c.chunk_id === chunkId ? 'chunk cited' : 'chunk'}>
            <span className="chunk-no muted small">
              {t('srcView.chunk', { n: c.index + 1 })}
              {c.page !== null && ` · ${t('srcView.page', { n: c.page })}`}
            </span>
            <p>{c.text}</p>
          </li>
        ))}
      </ol>
      {pager}
    </div>
  )
}
