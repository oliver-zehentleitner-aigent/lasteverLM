import { useState } from 'react'
import type { AudioContent } from '../../api/types'
import { t } from '../../i18n'
import { ClaimMarks } from '../OutputProvenance'

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
        <audio controls preload="metadata" src={src} onError={onError} onLoadedMetadata={() => setRefreshed(false)} />
      )}
      {content.transcript && content.transcript.length > 0 && <Transcript turns={content.transcript} speakerName={speakerName} />}
    </div>
  )
}

/** What is said, under the player. A narrator's paragraphs as plain text;
 *  a conversation with the speaker in front of each turn. */
function Transcript({ turns, speakerName }: { turns: NonNullable<AudioContent['transcript']>; speakerName: (speaker: string) => string }) {
  const labelled = turns.some((turn) => turn.speaker !== 'narrator')
  return (
    <section className="transcript" aria-label={t('audio.transcript')}>
      <h2>{t('audio.transcript')}</h2>
      {turns.map((turn, i) => (
        <p key={i} className={labelled ? `turn ${turn.speaker}` : undefined}>
          {labelled && <strong className="speaker">{speakerName(turn.speaker)}</strong>}
          {turn.text} <ClaimMarks claim={turn} text={turn.text} />
        </p>
      ))}
    </section>
  )
}
