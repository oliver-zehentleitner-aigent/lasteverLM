import { Suspense, lazy } from 'react'
import type {
  AudioContent,
  ChartContent,
  DecisionContent,
  InfographicContent,
  MindmapContent,
  OutputKind,
  OutputPhase,
  OutputStatus,
  QuizContent,
  FlashcardsContent,
  ReportContent,
  TableContent,
} from '../../api/types'
import { AudioView } from './AudioView'
import { DecisionView } from './DecisionView'

// recharts comes with it, loaded only when a chart output is opened
const ChartView = lazy(() => import('./ChartView'))
import { Generating } from './Generating'
import { InfographicView } from './InfographicView'
import { MindmapView } from './MindmapView'
import { QuizView } from './QuizView'
import { FlashcardsView } from './FlashcardsView'
import { ReportView } from './ReportView'
import { TableView } from './TableView'
import { t } from '../../i18n'
import type { LocateRequest } from '../../lib/locate'

interface Props {
  kind: OutputKind
  title: string
  status: OutputStatus
  error: string | null
  content: unknown
  /** a fresh presigned audio url, read when the current one has expired */
  onExpired?: () => Promise<string>
  /** a passage to show; only the mind map handles it here, the viewer the rest */
  locate?: LocateRequest | null
  /** an audio transcript's speaker as shown, from its role */
  speakerName?: (speaker: string) => string
  /** while it is made: since when, and the worker's step */
  createdAt?: string | null
  phase?: OutputPhase | null
}

/** Dispatches a document to its renderer by kind. Works for an owned output
 *  and for a shared one alike, which is why it takes fields, not an Output. */
export function OutputContent({ kind, title, status, error, content, onExpired, locate, speakerName, createdAt, phase }: Props) {
  // while it is made: its kind's shape, and what is really happening
  if (status === 'waiting') return <Generating kind={kind} createdAt={createdAt} phase={phase} fallback={t('content.waiting')} />
  if (status === 'processing') return <Generating kind={kind} createdAt={createdAt} phase={phase} retry={error} fallback={t('content.generating')} />
  if (status === 'failed') return <p className="error">{error ?? t('content.failed')}</p>
  if (content === null || content === undefined) return <p className="muted">{t('content.none')}</p>
  switch (kind) {
    case 'report':
      return <ReportView content={content as ReportContent} />
    case 'quiz':
      return <QuizView content={content as QuizContent} />
    case 'flashcards':
      return <FlashcardsView content={content as FlashcardsContent} title={title} />
    case 'table':
      return <TableView content={content as TableContent} title={title} />
    case 'mindmap':
      return <MindmapView content={content as MindmapContent} locate={locate ?? null} />
    case 'infographic':
      return <InfographicView content={content as InfographicContent} />
    case 'audio':
      return <AudioView content={content as AudioContent} onExpired={onExpired} speakerName={speakerName} />
    case 'decision':
      return <DecisionView content={content as DecisionContent} />
    case 'chart':
      return (
        <Suspense fallback={<p className="muted">{t('common.loading')}</p>}>
          <ChartView content={content as ChartContent} />
        </Suspense>
      )
    default:
      return <pre className="output-text">{JSON.stringify(content, null, 2)}</pre>
  }
}
