/** One branch's earn/spend/outstanding, visualized as a collected-total
 * ratio bar instead of three bare table cells. */
export default function BranchPerformanceCard({
  name,
  earned,
  spent,
  outstanding,
  labels,
}: {
  name: string
  earned: number
  spent: number
  outstanding: number
  labels: { earned: string; spent: string; outstanding: string }
}) {
  const total = earned + spent || 1
  const earnPct = Math.min(100, (earned / total) * 100)
  const spendPct = Math.min(100 - earnPct, (spent / total) * 100)

  return (
    <div className="branch-card">
      <div className="branch-card-head">
        <span className="branch-card-name">{name}</span>
      </div>
      <div className="ratio-bar-track">
        <div className="ratio-bar-earn" style={{ width: `${earnPct}%` }} />
        <div className="ratio-bar-spend" style={{ width: `${spendPct}%` }} />
      </div>
      <div className="branch-card-figures">
        <div className="branch-card-figure">
          <div className="branch-card-figure-label">{labels.earned}</div>
          <div className="branch-card-figure-value earn">{earned.toLocaleString()}</div>
        </div>
        <div className="branch-card-figure">
          <div className="branch-card-figure-label">{labels.spent}</div>
          <div className="branch-card-figure-value spend">{spent.toLocaleString()}</div>
        </div>
        <div className="branch-card-figure">
          <div className="branch-card-figure-label">{labels.outstanding}</div>
          <div className="branch-card-figure-value">{outstanding.toLocaleString()}</div>
        </div>
      </div>
    </div>
  )
}
