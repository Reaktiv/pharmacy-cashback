import type { DailyReportRow } from '../api/types'

export type Trend = { direction: 'up' | 'down' | 'flat'; text: string }

/** Last 7 days vs. the 7 days before that, computed from the real daily
 * series — never a fabricated number. Returns null when there isn't
 * enough history yet, or the prior week was zero (a percentage would be
 * meaningless there). */
export function weekOverWeekTrend(daily: DailyReportRow[], key: 'total_earned' | 'total_spent'): Trend | null {
  if (daily.length < 14) return null
  const sorted = [...daily].sort((a, b) => a.day.localeCompare(b.day))
  const last7 = sorted.slice(-7).reduce((sum, d) => sum + d[key], 0)
  const prev7 = sorted.slice(-14, -7).reduce((sum, d) => sum + d[key], 0)
  if (prev7 === 0) return null
  const pct = ((last7 - prev7) / prev7) * 100
  const direction = Math.abs(pct) < 1 ? 'flat' : pct > 0 ? 'up' : 'down'
  return { direction, text: `${pct > 0 ? '+' : ''}${pct.toFixed(0)}%` }
}
