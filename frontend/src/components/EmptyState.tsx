import type { ReactNode } from 'react'
import { IconPillBottle } from './Icons'

export default function EmptyState({
  icon,
  title,
  subtitle,
}: {
  icon?: ReactNode
  title: string
  subtitle?: string
}) {
  return (
    <div className="empty-state">
      {icon ?? <IconPillBottle />}
      <div className="empty-title">{title}</div>
      {subtitle && <div className="empty-sub">{subtitle}</div>}
    </div>
  )
}
