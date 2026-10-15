import { useRef } from 'react'
import type { ChartContent, ChartPoint, ChartSpec } from '../../api/types'
import { useChartColors, type ChartColors } from '../../hooks/useChartColors'
import { useCite } from '../../hooks/useCite'
import { allPoints, chartCsv, chartFileName, pointPassage, supportLine } from '../../lib/chartOutput'
import { t } from '../../i18n'
import { ChartFigure } from '../charts/ChartFigure'

/** A chart output: its charts one under the other, each with its values
 *  marked by the check (filled backed, hollow not backed, a diamond for a
 *  computed one), a click on a value opening its passage, PNG and CSV, and
 *  the values as a folded table with their passages. Loaded on demand with
 *  recharts, as the admin overview's charts are. */
export default function ChartView({ content }: { content: ChartContent }) {
  const colors = useChartColors()
  const charts = content.charts ?? []
  const line = supportLine(charts)
  return (
    <div className="chart-output">
      {line && <p className="muted small">{line}</p>}
      <p className="chart-legend muted small" aria-hidden="true">
        <span className="mark supported" /> {t('chartOut.legend.supported')}
        <span className="mark unsupported" /> {t('chartOut.legend.unsupported')}
        <span className="mark derived" /> {t('chartOut.legend.derived')}
      </p>
      {charts.map((c, i) => (
        <OneChart key={i} chart={c} colors={colors} />
      ))}
    </div>
  )
}

function OneChart({ chart, colors }: { chart: ChartSpec; colors: ChartColors }) {
  const cite = useCite()
  const box = useRef<HTMLDivElement>(null)
  const points = allPoints(chart)

  function open(p: ChartPoint, series: string) {
    const n = pointPassage(p)
    if (n !== null && cite) cite.cite(n, `${series} ${p.x} ${p.y}`)
  }

  function download(blob: Blob, name: string) {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = name
    a.click()
    URL.revokeObjectURL(a.href)
  }

  /** The drawn SVG onto a canvas over the panel colour, as PNG. */
  function png() {
    const svg = box.current?.querySelector('svg.recharts-surface')
    if (!svg) return
    const { width, height } = svg.getBoundingClientRect()
    const copy = svg.cloneNode(true) as SVGSVGElement
    copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    copy.setAttribute('width', String(width))
    copy.setAttribute('height', String(height))
    const img = new Image()
    img.onload = () => {
      const scale = 2
      const canvas = document.createElement('canvas')
      canvas.width = width * scale
      canvas.height = height * scale
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.fillStyle = colors.panel
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      canvas.toBlob((b) => b && download(b, chartFileName(chart.title, 'png')), 'image/png')
    }
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(copy))}`
  }

  return (
    <section className="chart-card one-chart">
      <header>
        <h3>{chart.title}</h3>
        <span className="muted small">{t(`chartOut.type.${chart.chart_type}`)}</span>
        <span className="actions no-print">
          <button type="button" className="link small" onClick={png}>
            {t('chartOut.png')}
          </button>
          <button type="button" className="link small" onClick={() => download(new Blob([chartCsv(chart)], { type: 'text/csv;charset=utf-8' }), chartFileName(chart.title, 'csv'))}>
            {t('chartOut.csv')}
          </button>
        </span>
      </header>
      <div ref={box} className="chart-body">
        <ChartFigure chart={chart} colors={colors} height={280} onPoint={open} />
      </div>
      {chart.note && <p className="muted small">{chart.note}</p>}
      <details className="chart-values">
        <summary>{t('chartOut.values', { n: points.length })}</summary>
        <table>
          <thead>
            <tr>
              <th>{chart.x_label}</th>
              {chart.series.length > 1 && <th />}
              <th>{chart.y_label}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {points.map(({ series, point }, i) => (
              <tr key={i} className={`support-${point.support}`}>
                <td>{String(point.x)}</td>
                {chart.series.length > 1 && <td className="muted">{series}</td>}
                <td className="num">{point.y}</td>
                <td>
                  <PointRefs point={point} series={series} onOpen={open} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  )
}

/** A value's passages as markers; a computed one says what it was
 *  computed from; an unbacked one carries the badge. */
function PointRefs({ point, series, onOpen }: { point: ChartPoint; series: string; onOpen: (p: ChartPoint, series: string) => void }) {
  const cite = useCite()
  const marker = (n: number) => (
    <button key={n} type="button" className={cite?.open === n ? 'cite open' : 'cite'} onClick={() => cite?.cite(n, `${series} ${point.x} ${point.y}`)}>
      {n}
    </button>
  )
  if (point.support === 'derived')
    return (
      <span className="small">
        <span className="muted">{t('chartOut.computedFrom')}</span> {(point.derived_from ?? []).map(marker)}
      </span>
    )
  return (
    <span className="small">
      {point.refs.map(marker)}
      {point.support === 'unsupported' && (
        <span className="badge support-unsupported" title={t('chartOut.unsupportedTitle')} onClick={() => onOpen(point, series)}>
          {t('chartOut.unsupported')}
        </span>
      )}
    </span>
  )
}
