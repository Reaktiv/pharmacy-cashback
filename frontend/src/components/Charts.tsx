/** Small hand-rolled grouped bar chart — no charting library (CLAUDE.md
 * §9). Colors are the validated chart pair from index.css
 * (--chart-earn / --chart-spend); see the dataviz palette check. */

import { useLanguage } from '../lib/i18n'

export interface DualBarDatum {
  label: string
  a: number
  b: number
}

const WIDTH = 720
const HEIGHT = 220
const PAD_LEFT = 6
const PAD_BOTTOM = 26
const PAD_TOP = 10

export function DualBarChart({
  data,
  seriesALabel,
  seriesBLabel,
  formatValue = (n: number) => n.toLocaleString(),
}: {
  data: DualBarDatum[]
  seriesALabel: string
  seriesBLabel: string
  formatValue?: (n: number) => string
}) {
  const { t } = useLanguage()
  if (data.length === 0) {
    return <p className="chart-empty">{t('chart_no_data')}</p>
  }

  const max = Math.max(1, ...data.flatMap((d) => [d.a, d.b]))
  const plotHeight = HEIGHT - PAD_BOTTOM - PAD_TOP
  const plotWidth = WIDTH - PAD_LEFT
  const groupWidth = plotWidth / data.length
  const barWidth = Math.max(3, Math.min(16, groupWidth / 2 - 6))
  const labelEvery = Math.max(1, Math.ceil(data.length / 8))

  const scaleY = (v: number) => (v / max) * plotHeight

  return (
    <div>
      <div className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-legend-swatch" style={{ background: 'var(--chart-earn)' }} />
          {seriesALabel}
        </span>
        <span className="chart-legend-item">
          <span className="chart-legend-swatch" style={{ background: 'var(--chart-spend)' }} />
          {seriesBLabel}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        role="img"
        aria-label={t('chart_bar_aria_label', { a: seriesALabel, b: seriesBLabel })}
      >
        <line
          x1={PAD_LEFT}
          y1={HEIGHT - PAD_BOTTOM}
          x2={WIDTH}
          y2={HEIGHT - PAD_BOTTOM}
          stroke="var(--border)"
          strokeWidth="1"
        />
        {data.map((d, i) => {
          const gx = PAD_LEFT + i * groupWidth
          const ah = scaleY(d.a)
          const bh = scaleY(d.b)
          const showLabel = i % labelEvery === 0 || i === data.length - 1
          return (
            <g key={`${d.label}-${i}`} className="chart-bar-group">
              <title>
                {`${d.label}\n${seriesALabel}: ${formatValue(d.a)}\n${seriesBLabel}: ${formatValue(d.b)}`}
              </title>
              <rect
                x={gx + groupWidth / 2 - barWidth - 2}
                y={HEIGHT - PAD_BOTTOM - ah}
                width={barWidth}
                height={Math.max(ah, 1)}
                rx="3"
                fill="var(--chart-earn)"
              />
              <rect
                x={gx + groupWidth / 2 + 2}
                y={HEIGHT - PAD_BOTTOM - bh}
                width={barWidth}
                height={Math.max(bh, 1)}
                rx="3"
                fill="var(--chart-spend)"
              />
              {showLabel && (
                <text
                  x={gx + groupWidth / 2}
                  y={HEIGHT - 8}
                  textAnchor="middle"
                  fontSize="9.5"
                  fill="var(--text-faint)"
                >
                  {d.label}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export interface PieDatum {
  label: string
  value: number
  color: string
}

const PIE_SIZE = 176
const PIE_STROKE = 32

export function PieChart({
  data,
  formatValue = (n: number) => n.toLocaleString(),
}: {
  data: PieDatum[]
  formatValue?: (n: number) => string
}) {
  const { t } = useLanguage()
  const total = data.reduce((sum, d) => sum + d.value, 0)

  if (total <= 0) {
    return <p className="chart-empty">{t('chart_no_data')}</p>
  }

  const radius = (PIE_SIZE - PIE_STROKE) / 2
  const circumference = 2 * Math.PI * radius
  let cumulative = 0

  return (
    <div style={{ display: 'flex', gap: '2rem', alignItems: 'center', flexWrap: 'wrap' }}>
      <svg
        viewBox={`0 0 ${PIE_SIZE} ${PIE_SIZE}`}
        width={PIE_SIZE}
        height={PIE_SIZE}
        role="img"
        aria-label={t('chart_pie_aria_label')}
      >
        <g transform={`rotate(-90 ${PIE_SIZE / 2} ${PIE_SIZE / 2})`}>
          {data.map((d) => {
            const fraction = d.value / total
            const fullDash = fraction * circumference
            const visibleDash = Math.max(0, fullDash - (data.length > 1 ? 2 : 0))
            const offset = -cumulative
            cumulative += fullDash
            return (
              <circle
                key={d.label}
                cx={PIE_SIZE / 2}
                cy={PIE_SIZE / 2}
                r={radius}
                fill="none"
                stroke={d.color}
                strokeWidth={PIE_STROKE}
                strokeDasharray={`${visibleDash} ${circumference - visibleDash}`}
                strokeDashoffset={offset}
              >
                <title>{`${d.label}: ${formatValue(d.value)} (${(fraction * 100).toFixed(1)}%)`}</title>
              </circle>
            )
          })}
        </g>
      </svg>
      <div className="chart-legend" style={{ flexDirection: 'column', gap: '0.65rem', margin: 0 }}>
        {data.map((d) => (
          <span className="chart-legend-item" key={d.label}>
            <span className="chart-legend-swatch" style={{ background: d.color }} />
            {d.label}:{' '}
            <strong style={{ color: 'var(--text)', fontWeight: 750 }}>{formatValue(d.value)}</strong>
            <span style={{ color: 'var(--text-faint)' }}>
              ({((d.value / total) * 100).toFixed(1)}%)
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
