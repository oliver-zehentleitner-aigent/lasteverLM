import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import type { AudioContent } from '../../api/types'
import { t } from '../../i18n'
import { ClaimMarks } from '../OutputProvenance'
import { activeTurn, timed } from '../../lib/audioSync'

interface Props {
  content: AudioContent
  /** fetch a fresh url; the url is presigned for one hour and re-issued
   *  on every read, so a tab left open outlives it */
  onExpired?: () => Promise<string>
  speakerName?: (speaker: string) => string
}

/** The audio player. It keeps the url it started with: every read of the
 *  document re-issues the url, and taking each new one from the output
 *  poll would restart playback on every tick. A load error is taken as an
 *  expired url once and answered with a fresh one; a second error in a
 *  row is shown, so a broken file does not refetch forever. */
export function AudioView({ content, onExpired, speakerName = (s) => s }: Props) {
  const [src, setSrc] = useState(content.url)
  const [refreshed, setRefreshed] = useState(false)
  const [failed, setFailed] = useState(false)
  const audio = useRef<HTMLAudioElement>(null)
  const turns = content.transcript ?? []
  // the entry being spoken, from the per-entry times; older audio has none and highlights nothing
  const [active, setActive] = useState(-1)
  const follows = timed(turns)

  function seek(i: number) {
    const el = audio.current
    const start = turns[i]?.start
    if (!el || start == null) return
    el.currentTime = start
    setActive(i)
    if (el.paused) void el.play().catch(() => {})
  }

  function onError() {
    if (!onExpired || refreshed) {
      setFailed(true)
      return
    }
    setRefreshed(true)
    onExpired().then(setSrc, () => setFailed(true))
  }

  // one block: centred in the viewer while it fits, from the top once it does not
  return (
    <div className="audio-view">
      {failed ? (
        <p className="error">{t('audio.failed')}</p>
      ) : (
        <audio
          ref={audio}
          controls
          preload="metadata"
          src={src}
          onError={onError}
          onLoadedMetadata={() => setRefreshed(false)}
          onTimeUpdate={follows ? (e) => setActive(activeTurn(turns, e.currentTarget.currentTime)) : undefined}
        />
      )}
      {turns.length > 0 && <Transcript turns={turns} speakerName={speakerName} active={active} onSeek={follows ? seek : undefined} />}
    </div>
  )
}

/** What is said, under the player. A narrator's paragraphs as plain text;
 *  a conversation with the speaker in front of each turn. With timings the
 *  entry being spoken is marked and kept in view, and a click (or Enter)
 *  on an entry plays from its start; a click on a citation marker stays a
 *  citation. */
function Transcript({
  turns,
  speakerName,
  active,
  onSeek,
}: {
  turns: NonNullable<AudioContent['transcript']>
  speakerName: (speaker: string) => string
  active: number
  onSeek?: (i: number) => void
}) {
  const labelled = turns.some((turn) => turn.speaker !== 'narrator')
  const list = useRef<HTMLElement>(null)

  useEffect(() => {
    if (active < 0) return
    const el = list.current?.querySelector<HTMLElement>(`[data-turn="${active}"]`)
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    el?.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' })
  }, [active])

  const click = (i: number) => (e: MouseEvent) => {
    if ((e.target as HTMLElement).closest('button, a')) return
    onSeek?.(i)
  }
  const key = (i: number) => (e: KeyboardEvent) => {
    if (e.target !== e.currentTarget || (e.key !== 'Enter' && e.key !== ' ')) return
    e.preventDefault()
    onSeek?.(i)
  }

  return (
    <section className={onSeek ? 'transcript timed' : 'transcript'} aria-label={t('audio.transcript')} ref={list}>
      <h2>{t('audio.transcript')}</h2>
      {turns.map((turn, i) => (
        <p
          key={i}
          data-turn={i}
          className={[labelled ? `turn ${turn.speaker}` : '', i === active ? 'speaking' : ''].join(' ').trim() || undefined}
          aria-current={i === active ? 'true' : undefined}
          {...(onSeek ? { role: 'button', tabIndex: 0, title: t('audio.playFrom'), onClick: click(i), onKeyDown: key(i) } : {})}
        >
          {labelled && <strong className="speaker">{speakerName(turn.speaker)}</strong>}
          {turn.text} <ClaimMarks claim={turn} text={turn.text} />
        </p>
      ))}
    </section>
  )
}
