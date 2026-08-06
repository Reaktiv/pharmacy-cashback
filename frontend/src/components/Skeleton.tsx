export function SkeletonLine({ width = '100%' }: { width?: string }) {
  return <div className="skeleton skeleton-line" style={{ width }} />
}

export function SkeletonStatGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="skeleton-stat-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton skeleton-stat-card" />
      ))}
    </div>
  )
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="skeleton-table">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonLine key={i} width={i % 2 === 0 ? '100%' : '82%'} />
      ))}
    </div>
  )
}
