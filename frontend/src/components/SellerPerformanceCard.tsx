import type { ReactNode } from 'react'
import { IconChevronDown } from './Icons'

/** One row in the seller performance list — replaces the plain sortable
 * table with a ranked card: an activity bar sized relative to the busiest
 * seller (activityRatio, 0..1, computed by the caller from real txn_count
 * figures — never fabricated), a flagged-count pill when relevant, and an
 * expand toggle that reveals the existing transaction history/pie
 * breakdown in place. */
export default function SellerPerformanceCard({
  rank,
  name,
  txnCount,
  avgCheck,
  flaggedCount,
  activityRatio,
  labels,
  expanded,
  expandable,
  onToggle,
  children,
}: {
  rank: number
  name: string
  txnCount: number
  avgCheck: number
  flaggedCount: number
  activityRatio: number
  labels: { transactions: string; avgCheck: string; flagged: string }
  expanded: boolean
  expandable: boolean
  onToggle: () => void
  children?: ReactNode
}) {
  return (
    <div className="perf-card">
      <div className={`perf-card-row${expandable ? '' : ' static'}`} onClick={expandable ? onToggle : undefined}>
        <span className={`perf-rank${rank === 1 ? ' top' : ''}`}>{rank}</span>
        <div className="perf-main">
          <div className="perf-name-row">
            {name}
            {flaggedCount > 0 && (
              <span className="pill failed">
                {flaggedCount} {labels.flagged}
              </span>
            )}
          </div>
          <div className="perf-meta">
            <span>
              {labels.transactions}: <strong>{txnCount.toLocaleString()}</strong>
            </span>
            <span>
              {labels.avgCheck}: <strong>{avgCheck.toLocaleString()}</strong>
            </span>
          </div>
          <div className="perf-bar-track">
            <div
              className={`perf-bar-fill${flaggedCount > 0 ? ' warn' : ''}`}
              style={{ width: `${Math.max(4, Math.round(activityRatio * 100))}%` }}
            />
          </div>
        </div>
        {expandable && (
          <span className="perf-side">
            <IconChevronDown className={`row-chevron${expanded ? ' expanded' : ''}`} />
          </span>
        )}
      </div>
      {expanded && <div className="perf-detail">{children}</div>}
    </div>
  )
}
