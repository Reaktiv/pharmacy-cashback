import { useState } from 'react'
import { apiFetch, ApiError } from '../api/client'
import { useLanguage } from '../lib/i18n'
import { IconAlertCircle } from './Icons'

/** One-click is_active flip, shared by the three activation hierarchies in
 * CLAUDE.md §3 (superadmin → Tenant, tenant_admin → Branch, branch_manager
 * → Seller) — same PATCH {is_active} shape against a different endpoint
 * each time, so this is parameterized rather than copied three times. */
export default function ActiveToggle<T extends { is_active: boolean }>({
  endpoint,
  isActive,
  onSaved,
}: {
  endpoint: string
  isActive: boolean
  onSaved: (updated: T) => void
}) {
  const { t } = useLanguage()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleClick = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const updated = await apiFetch<T>(endpoint, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !isActive }),
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('active_toggle_error'))
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
        onClick={handleClick}
        disabled={submitting}
        style={{ marginTop: '0.5rem' }}
      >
        {submitting ? t('saving') : isActive ? t('deactivate_button') : t('activate_button')}
      </button>
    </div>
  )
}
