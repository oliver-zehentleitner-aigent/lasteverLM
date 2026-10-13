import { useState } from 'react'
import type { AudioContent } from '../../api/types'

interface Props {
  content: AudioContent
  /** fetch a fresh url; the url is presigned for one hour and re-issued
   *  on every read, so a tab left open outlives it */
  onExpired?: () => Promise<string>
}

/** The audio player. It keeps the url it started with: every read of the
 *  document re-issues the url, and taking each new one from the output
 *  poll would restart playback on every tick. A load error is taken as an
 *  expired url once and answered with a fresh one; a second error in a
 *  row is shown, so a broken file does not refetch forever. */
export function AudioView({ content, onExpired }: Props) {
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

  // one block, centred in the viewer by the stylesheet
  return (
    <div className="audio-view">
      {failed ? (
        <p className="error">The audio could not be loaded.</p>
      ) : (
        <audio controls preload="metadata" src={src} onError={onError} onLoadedMetadata={() => setRefreshed(false)} />
      )}
    </div>
  )
}
