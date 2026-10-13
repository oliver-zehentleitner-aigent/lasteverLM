import type {
  AudioContent,
  InfographicContent,
  MindmapContent,
  OutputKind,
  OutputStatus,
  QuizContent,
  ReportContent,
  TableContent,
} from '../../api/types'
import { AudioView } from './AudioView'
import { InfographicView } from './InfographicView'
import { MindmapView } from './MindmapView'
import { QuizView } from './QuizView'
import { ReportView } from './ReportView'
import { TableView } from './TableView'

interface Props {
  kind: OutputKind
  title: string
  status: OutputStatus
  error: string | null
  content: unknown
  /** a fresh presigned audio url, read when the current one has expired */
  onExpired?: () => Promise<string>
}

/** Dispatches a document to its renderer by kind. Works for an owned output
 *  and for a shared one alike, which is why it takes fields, not an Output. */
export function OutputContent({ kind, title, status, error, content, onExpired }: Props) {
  if (status === 'waiting') return <p className="muted">Waiting for the sources to finish processing…</p>
  if (status === 'processing') return <p className="muted">Generating…</p>
  if (status === 'failed') return <p className="error">{error ?? 'Generation failed.'}</p>
  if (content === null || content === undefined) return <p className="muted">No content.</p>
  switch (kind) {
    case 'report':
      return <ReportView content={content as ReportContent} />
    case 'quiz':
      return <QuizView content={content as QuizContent} />
    case 'table':
      return <TableView content={content as TableContent} title={title} />
    case 'mindmap':
      return <MindmapView content={content as MindmapContent} />
    case 'infographic':
      return <InfographicView content={content as InfographicContent} />
    case 'audio':
      return <AudioView content={content as AudioContent} onExpired={onExpired} />
    default:
      return <pre className="output-text">{JSON.stringify(content, null, 2)}</pre>
  }
}
