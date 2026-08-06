import { useEffect, useRef, useState, type ReactNode } from 'react'
import { IconAlertTriangle } from './Icons'
import { useLanguage } from '../lib/i18n'

type ConfirmDialogProps = {
  open: boolean
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'danger' | 'default'
  confirming?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Modern replacement for window.confirm — used for both destructive
 * deletes and the logout prompt, so the whole app has one consistent,
 * accessible confirmation surface instead of the native browser dialog. */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  tone = 'default',
  confirming = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useLanguage()
  const resolvedConfirmLabel = confirmLabel ?? t('confirm_default')
  const resolvedCancelLabel = cancelLabel ?? t('cancel')
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    cancelRef.current?.focus()
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div className="modal-overlay" onMouseDown={onCancel}>
      <div
        className="modal-card"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className={`modal-icon${tone === 'danger' ? ' danger' : ''}`}>
          <IconAlertTriangle />
        </div>
        <h3 id="confirm-dialog-title" className="modal-title">
          {title}
        </h3>
        {description && <p className="modal-description">{description}</p>}
        <div className="modal-actions">
          <button ref={cancelRef} type="button" className="secondary" onClick={onCancel} disabled={confirming}>
            {resolvedCancelLabel}
          </button>
          <button
            type="button"
            className={tone === 'danger' ? 'danger' : ''}
            onClick={onConfirm}
            disabled={confirming}
          >
            {confirming ? t('in_progress') : resolvedConfirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

type ConfirmStep = { title: string; description?: ReactNode; confirmLabel?: string }

type DoubleConfirmDialogProps = {
  open: boolean
  step1: ConfirmStep
  step2: ConfirmStep
  confirming?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Two sequential ConfirmDialogs for actions destructive enough to warrant
 * asking twice — e.g. deleting a branch/tenant, where the second step calls
 * out the ledger history that goes with it. Resets back to step 1 every
 * time it's reopened. */
export function DoubleConfirmDialog({
  open,
  step1,
  step2,
  confirming = false,
  onConfirm,
  onCancel,
}: DoubleConfirmDialogProps) {
  const { t } = useLanguage()
  const [step, setStep] = useState<1 | 2>(1)

  useEffect(() => {
    if (open) setStep(1)
  }, [open])

  if (!open) return null

  const active = step === 1 ? step1 : step2

  return (
    <ConfirmDialog
      open
      title={active.title}
      description={active.description}
      confirmLabel={active.confirmLabel ?? (step === 1 ? t('continue_button') : t('delete_fully_confirm'))}
      tone="danger"
      confirming={step === 2 ? confirming : false}
      onConfirm={step === 1 ? () => setStep(2) : onConfirm}
      onCancel={onCancel}
    />
  )
}
