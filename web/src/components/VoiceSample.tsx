import { useEffect, useRef, useState } from 'react'
import { rag } from '../api/rag'
import { useEstimate } from '../hooks/useEstimate'
import { t } from '../i18n'
import { priceLabel } from '../lib/estimate'

interface Props {
  voice: string
  speed?: number
  /** a catalogue language code; omitted lets rag use its default */
  language?: string
}

/** Plays a short sample of a voice at the chosen speed and language. The
 *  URL is fetched on click, never ahead, since the first request for a
 *  combination is synthesized and costs a little credit; its estimate is
 *  in the tooltip. */
export function VoiceSample({ voice, speed, language }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const price = useEstimate({ action: 'voice_sample' })
  const title = price && 'estimate' in price ? `${t('sample.title')} ${t('price.sample', { price: priceLabel(price.estimate) })}` : t('sample.title')

  // a new choice stops the sample of the old one
  useEffect(() => () => audio.current?.pause(), [voice, speed, language])

  async function play() {
    setError(null)
    setBusy(true)
    try {
      const { url } = await rag.voiceSample(voice, speed, language)
      audio.current?.pause()
      audio.current = new Audio(url)
      await audio.current.play()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="voice-sample">
      <button type="button" className="secondary small" title={title} disabled={busy || !voice} onClick={() => void play()}>
        {busy ? t('sample.loading') : t('sample.play')}
      </button>
      {error && <span className="error small">{error}</span>}
    </span>
  )
}
