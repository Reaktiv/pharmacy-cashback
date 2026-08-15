import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useLanguage } from '../lib/i18n'
import SellersList from '../components/SellersList'
import DetailDrawer from '../components/DetailDrawer'
import { IconAlertCircle, IconPlus } from '../components/Icons'

/** Only the branch manager adds sellers (CLAUDE.md §3) — the tenant admin
 * only sees a read-only version of this list embedded in the Dorixona
 * overview page (TenantAdminPage), so this whole route is branch-manager
 * only (see App.tsx). */
function AddSellerDrawer({
  open,
  branchId,
  onClose,
  onCreated,
}: {
  open: boolean
  branchId: string
  onClose: () => void
  onCreated: () => void
}) {
  const { t } = useLanguage()
  const queryClient = useQueryClient()
  const [phone, setPhone] = useState('')
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [dailyLimit, setDailyLimit] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const reset = () => {
    setPhone('')
    setFullName('')
    setUsername('')
    setPassword('')
    setDailyLimit('')
    setFormError(null)
  }

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    setSubmitting(true)
    try {
      await apiFetch('/api/sellers/', {
        method: 'POST',
        body: JSON.stringify({
          branch: Number(branchId),
          phone,
          full_name: fullName,
          username,
          password,
          daily_txn_limit: dailyLimit.trim() === '' ? null : Number(dailyLimit),
        }),
      })
      queryClient.invalidateQueries({ queryKey: ['sellers'] })
      reset()
      onCreated()
    } catch (err) {
      setFormError(err instanceof ApiError ? JSON.stringify(err.data) : t('sellers_create_error'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <DetailDrawer
      open={open}
      title={t('sellers_add_heading')}
      onClose={() => {
        reset()
        onClose()
      }}
    >
      <form onSubmit={handleCreate}>
        {formError && (
          <div className="error-banner">
            <IconAlertCircle />
            <span>{formError}</span>
          </div>
        )}
        <div className="field">
          <label htmlFor="seller-name">{t('field_full_name')}</label>
          <input id="seller-name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="seller-phone">{t('field_phone')}</label>
          <input
            id="seller-phone"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder={t('phone_placeholder')}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="seller-username">{t('field_login')}</label>
          <input id="seller-username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="seller-password">{t('field_password')}</label>
          <input
            id="seller-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="seller-daily-limit">{t('th_daily_limit')}</label>
          <input
            id="seller-daily-limit"
            type="number"
            min={0}
            step={1}
            value={dailyLimit}
            onChange={(e) => setDailyLimit(e.target.value)}
            placeholder={t('unlimited')}
          />
          <p className="hint">{t('field_daily_limit_hint')}</p>
        </div>
        <button type="submit" disabled={!branchId || submitting}>
          <IconPlus />
          {submitting ? t('saving') : t('sellers_add_heading')}
        </button>
      </form>
    </DetailDrawer>
  )
}

export default function SellersPage() {
  const { user } = useAuth()
  const { t } = useLanguage()
  const isBranchManager = user?.role === 'branch_manager'

  const [addOpen, setAddOpen] = useState(false)

  return (
    <div>
      <div className="section-head" style={{ marginTop: 0 }}>
        <h2>{t('sellers_heading')}</h2>
        {isBranchManager && (
          <button type="button" onClick={() => setAddOpen(true)}>
            <IconPlus />
            {t('sellers_add_heading')}
          </button>
        )}
      </div>

      <SellersList canManage={isBranchManager} />

      {isBranchManager && (
        <AddSellerDrawer
          open={addOpen}
          branchId={user?.branchId ? String(user.branchId) : ''}
          onClose={() => setAddOpen(false)}
          onCreated={() => setAddOpen(false)}
        />
      )}
    </div>
  )
}
