import { useState, type ReactNode } from 'react'
import { apiFetch, ApiError } from '../api/client'
import { useLanguage } from '../lib/i18n'
import { IconAlertCircle } from './Icons'
import ConfirmDialog from './ConfirmDialog'

/** One-click is_active flip, shared by the three activation hierarchies in
 * CLAUDE.md §3 (superadmin → Tenant, tenant_admin → Branch, branch_manager
 * → Seller) — same PATCH {is_active} shape against a different endpoint
 * each time, so this is parameterized rather than copied three times.
 *
 * Deactivating locks people out, so it always goes through a confirmation
 * step; re-activating is harmless and fires immediately. Callers may pass
 * `confirmDescription` to spell out what specifically breaks. */
export default function ActiveToggle<T extends { is_active: boolean }>({
  endpoint,
  isActive,
  onSaved,
  confirmDescription,
}: {
  endpoint: string
  isActive: boolean
  onSaved: (updated: T) => void
  confirmDescription?: ReactNode
}) {
  const { t } = useLanguage()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const updated = await apiFetch<T>(endpoint, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !isActive }),
      })
      onSaved(updated)
      setConfirmOpen(false)
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('active_toggle_error'))
      setConfirmOpen(false)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      {error && (
        <div className="error-banner" style={{ marginTop: '0.5rem' }}>
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}
      <button
        type="button"
        className={isActive ? 'ghost danger sm' : 'ghost sm'}
        onClick={() => (isActive ? setConfirmOpen(true) : submit())}
        disabled={submitting}
        style={{ marginTop: '0.5rem' }}
      >
        {submitting ? t('saving') : isActive ? t('deactivate_button') : t('activate_button')}
      </button>

      <ConfirmDialog
        open={confirmOpen}
        title={t('deactivate_confirm_title')}
        description={confirmDescription ?? t('deactivate_confirm_description')}
        confirmLabel={t('deactivate_button')}
        tone="danger"
        confirming={submitting}
        onConfirm={submit}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
