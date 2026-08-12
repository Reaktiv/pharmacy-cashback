import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'
import { apiFetch, apiFetchObjectUrl, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Branch, Tenant } from '../api/types'
import type { LayoutOutletContext } from '../components/Layout'
import { useLanguage } from '../lib/i18n'
import {
  IconAlertCircle,
  IconCheckCircle,
  IconPlus,
  IconImagePicture,
  IconX,
} from '../components/Icons'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

/** BranchSerializer.validate() returns {detail: "..."} for the branch-limit
 * guard (apps/accounts/serializers.py) — surface that message directly
 * instead of a raw JSON blob, same convention as BroadcastsPage's
 * extractDetailError for the broadcast quota guard. Raised via
 * serializers.ValidationError (unlike the broadcast guard's plain
 * Response({"detail": ...})), so DRF normalizes the value into a
 * single-item list rather than a bare string — accept either shape. */
function extractDetailError(err: unknown): string | null {
  if (!(err instanceof ApiError) || typeof err.data !== 'object' || err.data === null) return null
  const value = (err.data as Record<string, unknown>).detail
  if (typeof value === 'string') return value
  if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  return null
}

function useAutoDismiss(flag: boolean, onDone: () => void, ms = 3200) {
  useEffect(() => {
    if (!flag) return
    const timer = setTimeout(onDone, ms)
    return () => clearTimeout(timer)
  }, [flag, onDone, ms])
}

const LOGO_MAX_BYTES = 5 * 1024 * 1024

/** Lets the tenant admin rename their own pharmacy and pick its logo — both
 * then show up everywhere the brand appears for every account scoped to
 * this tenant (sidebar/topbar for tenant_admin and branch_manager via
 * Layout.tsx, the seller-web till page, CLAUDE.md-adjacent branding).
 * Renaming also pushes the new name to the tenant's Telegram bot as its
 * display name (apps/bot/tasks.py sync_bot_display_name), server-side. */
function PharmacyIdentitySection({ tenant, onSaved }: { tenant: Tenant; onSaved: (t: Tenant) => void }) {
  const { t } = useLanguage()
  const { refreshBranding } = useOutletContext<LayoutOutletContext>()
  const inputRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState(tenant.name)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [logoPreview, setLogoPreview] = useState<string | null>(null)
  const [removeLogo, setRemoveLogo] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  useAutoDismiss(saved, () => setSaved(false))

  useEffect(() => {
    setName(tenant.name)
    if (!tenant.has_logo) {
      setLogoUrl(null)
      return
    }
    let cancelled = false
    apiFetchObjectUrl('/api/me/tenant-logo/').then((url) => {
      if (cancelled) URL.revokeObjectURL(url)
      else setLogoUrl(url)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant.has_logo])

  useEffect(() => {
    return () => {
      if (logoPreview) URL.revokeObjectURL(logoPreview)
    }
  }, [logoPreview])

  const handleFile = (file: File) => {
    setError(null)
    if (!file.type.startsWith('image/')) {
      setError(t('profile_avatar_invalid_type'))
      return
    }
    if (file.size > LOGO_MAX_BYTES) {
      setError(t('profile_avatar_too_large', { size: LOGO_MAX_BYTES / (1024 * 1024) }))
      return
    }
    if (logoPreview) URL.revokeObjectURL(logoPreview)
    setLogoFile(file)
    setLogoPreview(URL.createObjectURL(file))
    setRemoveLogo(false)
  }

  const handleRemoveLogo = () => {
    if (logoPreview) URL.revokeObjectURL(logoPreview)
    setLogoFile(null)
    setLogoPreview(null)
    setRemoveLogo(true)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSaved(false)
    setSubmitting(true)
    try {
      const formData = new FormData()
      formData.append('name', name)
      if (logoFile) formData.append('logo', logoFile)
      if (removeLogo) formData.append('remove_logo', 'true')
      const updated = await apiFetch<Tenant>(`/api/tenants/${tenant.id}/`, {
        method: 'PATCH',
        body: formData,
      })
      onSaved(updated)
      refreshBranding()
      setLogoFile(null)
      setLogoPreview(null)
      setRemoveLogo(false)
      setSaved(true)
    } catch (err) {
      setError(
        extractDetailError(err) ??
          (err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_identity_save_error')),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const shownLogo = logoPreview ?? (!removeLogo ? logoUrl : null)

  return (
    <form onSubmit={handleSubmit}>
      {error && (
        <div className="error-banner">
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}
      {saved && (
        <div className="toast">
          <IconCheckCircle />
          {t('tenant_detail_saved_toast')}
        </div>
      )}

      <div className="profile-avatar-picker">
        <div className={`profile-avatar-preview${shownLogo ? ' has-image' : ''}`}>
          {shownLogo ? <img src={shownLogo} alt="" /> : <span>{name.slice(0, 2).toUpperCase()}</span>}
        </div>
        <div className="profile-avatar-actions">
          <button type="button" className="ghost sm" onClick={() => inputRef.current?.click()}>
            <IconImagePicture />
            {t('tenant_admin_change_logo')}
          </button>
          {shownLogo && (
            <button type="button" className="ghost sm danger" onClick={handleRemoveLogo}>
              <IconX />
              {t('tenant_admin_remove_logo')}
            </button>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) handleFile(file)
          }}
        />
      </div>

      <div className="field wide">
        <label htmlFor="tenant-name">{t('field_tenant_name')}</label>
        <input id="tenant-name" value={name} onChange={(e) => setName(e.target.value)} required />
      </div>
      <button type="submit" disabled={submitting}>
        {submitting ? t('saving') : t('save')}
      </button>
    </form>
  )
}

function RateForm({ tenant, onSaved }: { tenant: Tenant; onSaved: (t: Tenant) => void }) {
  const { t } = useLanguage()
  const [rate, setRate] = useState(tenant.cashback_rate)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  useAutoDismiss(saved, () => setSaved(false))

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSaved(false)
    setSubmitting(true)
    try {
      const updated = await apiFetch<Tenant>(`/api/tenants/${tenant.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ cashback_rate: rate }),
      })
      onSaved(updated)
      setSaved(true)
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_rate_update_error'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {error && (
        <div className="error-banner">
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}
      {saved && (
        <div className="toast">
          <IconCheckCircle />
          {t('tenant_admin_rate_updated_toast')}
        </div>
      )}
      <div className="field">
        <label htmlFor="rate">{t('field_cashback_rate')}</label>
        <input id="rate" type="number" step="0.01" min="0" value={rate} onChange={(e) => setRate(e.target.value)} />
        <p className="hint">{t('hint_rate_format', { ten: 10, zeroTen: '0.10' })}</p>
      </div>
      <button type="submit" disabled={submitting}>
        {submitting ? t('saving') : t('tenant_admin_save_rate_button')}
      </button>
    </form>
  )
}

/** Just the "create a branch" form — the branch list itself now lives on
 * the Dorixona overview page (TenantAdminPage). */
function AddBranchForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useLanguage()
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  useAutoDismiss(saved, () => setSaved(false))

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSaved(false)
    setSubmitting(true)
    try {
      await apiFetch('/api/branches/', {
        method: 'POST',
        body: JSON.stringify({ name, address }),
      })
      setName('')
      setAddress('')
      setSaved(true)
      onCreated()
    } catch (err) {
      setError(
        extractDetailError(err) ??
          (err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_branch_create_error')),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleCreate}>
      {error && (
        <div className="error-banner">
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}
      {saved && (
        <div className="toast">
          <IconCheckCircle />
          {t('tenant_admin_add_branch_button')}
        </div>
      )}
      <div className="form-grid" style={{ alignItems: 'flex-end' }}>
        <div className="field">
          <label htmlFor="branch-name">{t('field_new_branch_name')}</label>
          <input id="branch-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="branch-address">{t('field_address')}</label>
          <input id="branch-address" value={address} onChange={(e) => setAddress(e.target.value)} />
        </div>
      </div>
      <button type="submit" disabled={submitting}>
        <IconPlus />
        {submitting ? t('saving') : t('tenant_admin_add_branch_button')}
      </button>
    </form>
  )
}

/** Just the "assign an admin to a branch" form — the branch admins list
 * itself now lives on the Dorixona overview page (TenantAdminPage). */
function AddBranchManagerForm() {
  const { t } = useLanguage()
  const [branches, setBranches] = useState<Branch[] | null>(null)
  const [branchId, setBranchId] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  useAutoDismiss(saved, () => setSaved(false))

  useEffect(() => {
    apiFetch<Branch[] | { results: Branch[] }>('/api/branches/').then((data) => setBranches(asArray(data)))
  }, [])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSaved(false)
    setSubmitting(true)
    try {
      await apiFetch('/api/branch-managers/', {
        method: 'POST',
        body: JSON.stringify({ branch: Number(branchId), username, password }),
      })
      setUsername('')
      setPassword('')
      setSaved(true)
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_manager_create_error'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleCreate}>
      {error && (
        <div className="error-banner">
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}
      {saved && (
        <div className="toast">
          <IconCheckCircle />
          {t('tenant_admin_assign_manager_card_heading')}
        </div>
      )}
      <div className="form-grid" style={{ alignItems: 'flex-end' }}>
        <div className="field">
          <label htmlFor="manager-branch">{t('field_branch')}</label>
          <select id="manager-branch" value={branchId} onChange={(e) => setBranchId(e.target.value)} required>
            <option value="" disabled>
              {t('field_branch_select_placeholder')}
            </option>
            {(branches ?? []).map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="manager-username">{t('field_login')}</label>
          <input id="manager-username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="manager-password">{t('field_password')}</label>
          <input
            id="manager-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
      </div>
      <button type="submit" disabled={!branchId || submitting}>
        <IconPlus />
        {submitting ? t('saving') : t('tenant_admin_add_manager_button')}
      </button>
    </form>
  )
}

/** The tenant admin's "Sozlamalar" page: everything that configures the
 * pharmacy rather than just listing/managing its people — identity
 * (name+logo), cashback rate, broadcast quota, and the two "create" forms
 * whose resulting lists live on the Dorixona overview page instead. */
export default function TenantSettingsPage() {
  const { user } = useAuth()
  const { t } = useLanguage()
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    if (!user?.tenantId) return
    apiFetch<Tenant>(`/api/tenants/${user.tenantId}/`)
      .then(setTenant)
      .catch((err) => setError(err.message))
  }

  useEffect(load, [user?.tenantId])

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error}</span>
      </div>
    )
  }
  if (!tenant) return <div className="card" style={{ minHeight: '12rem' }} />

  return (
    <div>
      <span className="eyebrow">{t('eyebrow_tenant')}</span>
      <h2 style={{ marginBottom: '1.5rem' }}>{t('nav_tenant_settings')}</h2>

      <div className="card">
        <div className="card-title-row">
          <h3>{t('tenant_admin_identity_card_heading')}</h3>
        </div>
        <PharmacyIdentitySection tenant={tenant} onSaved={setTenant} />
      </div>

      <div className="card">
        <div className="card-title-row">
          <h3>{t('tenant_admin_rate_card_heading')}</h3>
        </div>
        <RateForm tenant={tenant} onSaved={setTenant} />
      </div>

      <div className="card">
        <div className="card-title-row">
          <h3>{t('tenant_admin_quota_card_heading')}</h3>
        </div>
        <p style={{ marginTop: 0, marginBottom: 0 }}>
          {t('tenant_detail_quota_usage', {
            used: tenant.broadcasts_sent_this_month,
            quota: tenant.broadcast_quota === null ? '∞' : tenant.broadcast_quota,
          })}
        </p>
      </div>

      <div className="card">
        <div className="card-title-row">
          <h3>{t('tenant_admin_add_branch_card_heading')}</h3>
        </div>
        <AddBranchForm onCreated={load} />
      </div>

      <div className="card">
        <div className="card-title-row">
          <h3>{t('tenant_admin_assign_manager_card_heading')}</h3>
        </div>
        <AddBranchManagerForm />
      </div>
    </div>
  )
}
