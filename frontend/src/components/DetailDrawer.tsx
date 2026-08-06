import { useEffect, type ReactNode } from 'react'
import { IconX } from './Icons'
import { useLanguage } from '../lib/i18n'

type DetailDrawerProps = {
  open: boolean
  title: string
  subtitle?: string
  avatarLabel?: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}

/** Slide-in detail panel: click a row to open it, view its fields, act on
 * it (e.g. delete) from the footer. Used wherever a table row doesn't
 * warrant a whole page of its own (branch managers, sellers). */
export default function DetailDrawer({
  open,
  title,
  subtitle,
  avatarLabel,
  onClose,
  children,
  footer,
}: DetailDrawerProps) {
  const { t } = useLanguage()
  useEffect(() => {
    if (!open) return
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="drawer-overlay" onMouseDown={onClose}>
      <div
        className="drawer-panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="drawer-header">
          <div>
            {avatarLabel && <div className="drawer-avatar">{avatarLabel}</div>}
            <h3 className="modal-title">{title}</h3>
            {subtitle && <p className="text-muted" style={{ margin: 0, fontSize: '0.85rem' }}>{subtitle}</p>}
          </div>
          <button type="button" className="ghost" onClick={onClose} aria-label={t('close')}>
            <IconX />
          </button>
        </div>

        <div className="drawer-fields">{children}</div>

        {footer && <div className="drawer-footer">{footer}</div>}
      </div>
    </div>
  )
}

export function DrawerField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="drawer-field-label">{label}</p>
      <div className="drawer-field-value">{value}</div>
    </div>
  )
}
