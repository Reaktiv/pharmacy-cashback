import type { ReactNode } from 'react'
import { IconTrendUp, IconTrendDown } from './Icons'

/** Direction is derived by the caller from real deltas (e.g. last 7 days
 * vs. the previous 7) — never fabricated. `text` is the already-formatted
 * label (e.g. "+12.4%" or "3 ta ko'p"). */
export function TrendBadge({ direction, text }: { direction: 'up' | 'down' | 'flat'; text: string }) {
  return (
    <span className={`trend-badge ${direction}`}>
      {direction === 'up' && <IconTrendUp />}
      {direction === 'down' && <IconTrendDown />}
      {text}
    </span>
  )
}

export default function StatCard({
  icon,
  label,
  value,
  sub,
  tone,
  trend,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'primary' | 'teal' | 'warning' | 'success'
  trend?: { direction: 'up' | 'down' | 'flat'; text: string }
}) {
  return (
    <div className={`stat-card${tone && tone !== 'primary' ? ` ${tone}` : ''}`}>
      <div className="stat-card-top">
        <div className="stat-card-icon">{icon}</div>
        {trend && <TrendBadge direction={trend.direction} text={trend.text} />}
      </div>
      <div className="stat-card-label">{label}</div>
      <div className="stat-card-value">{value}</div>
      {sub !== undefined && <div className="stat-card-sub">{sub}</div>}
    </div>
  )
}
