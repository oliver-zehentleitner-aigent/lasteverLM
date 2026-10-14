import { t } from '../i18n'

interface Props {
  files: { transcribed: string; original: string | null }
}

/** The play button that mounts a player for one row, so a list of audio
 *  sources loads nothing until one is asked for. */
export function PlayButton({ open, name, onToggle }: { open: boolean; name: string; onToggle: () => void }) {
  const label = open ? t('audio.close', { name }) : t('audio.play', { name })
  return (
    <button type="button" className="icon play" aria-pressed={open} aria-label={label} title={label} onClick={onToggle}>
      {open ? '■' : '▶'}
    </button>
  )
}

/** What was transcribed, to listen to and to download, and the upload as
 *  it came when it was converted first. The URLs are taken when the row
 *  opens, so a refreshed list does not restart the player. */
export function AudioCheck({ files }: Props) {
  return (
    <div className="audio-view audio-check">
      <audio controls autoPlay preload="none" src={files.transcribed} />
      <span className="audio-files small">
        <a href={files.transcribed} download target="_blank" rel="noopener noreferrer">
          {t('audio.transcribed')}
        </a>
        {files.original && (
          <a href={files.original} download target="_blank" rel="noopener noreferrer">
            {t('audio.original')}
          </a>
        )}
      </span>
    </div>
  )
}
