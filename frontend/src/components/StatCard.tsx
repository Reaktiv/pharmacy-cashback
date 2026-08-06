import type { ReactNode } from 'react'

export default function StatCard({
  icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'primary' | 'teal' | 'warning' | 'success'
}) {
  return (
    <div className={`stat-card${tone && tone !== 'primary' ? ` ${tone}` : ''}`}>
      <div className="stat-card-icon">{icon}</div>
      <div className="stat-card-label">{label}</div>
      <div className="stat-card-value">{value}</div>
      {sub !== undefined && <div className="stat-card-sub">{sub}</div>}
    </div>
  )
}
