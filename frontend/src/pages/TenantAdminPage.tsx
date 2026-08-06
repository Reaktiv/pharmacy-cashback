import { useEffect, useState, type FormEvent } from 'react'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Branch, BranchManager, Tenant } from '../api/types'
import { activeStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import EmptyState from '../components/EmptyState'
import { SkeletonTable } from '../components/Skeleton'
import ConfirmDialog, { DoubleConfirmDialog } from '../components/ConfirmDialog'
import DetailDrawer, { DrawerField } from '../components/DetailDrawer'
import {
  IconAlertCircle,
  IconCheckCircle,
  IconPlus,
  IconBuilding,
  IconUsers,
  IconClipboardEmpty,
  IconTrash,
} from '../components/Icons'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

function useAutoDismiss(flag: boolean, onDone: () => void, ms = 3200) {
  useEffect(() => {
    if (!flag) return
    const timer = setTimeout(onDone, ms)
    return () => clearTimeout(timer)
  }, [flag, onDone, ms])
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

function BranchesSection() {
  const { t, language } = useLanguage()
  const [branches, setBranches] = useState<Branch[] | null>(null)
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [error, setError] = useState<string | null>(null)

  const [selected, setSelected] = useState<Branch | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const load = () => {
    apiFetch<Branch[] | { results: Branch[] }>('/api/branches/').then((data) =>
      setBranches(Array.isArray(data) ? data : data.results)
    )
  }

  useEffect(load, [])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await apiFetch('/api/branches/', {
        method: 'POST',
        body: JSON.stringify({ name, address }),
      })
      setName('')
      setAddress('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_branch_create_error'))
    }
  }

  const handleDelete = async () => {
    if (!selected) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await apiFetch(`/api/branches/${selected.id}/`, { method: 'DELETE' })
      setConfirmDeleteOpen(false)
      setSelected(null)
      load()
    } catch (err) {
      setDeleteError(err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_branch_delete_error'))
    } finally {
      setDeleting(false)
    }
  }

  if (!branches) return <SkeletonTable rows={4} />

  return (
    <div>
      <div className="table-card">
        {branches.length === 0 ? (
          <EmptyState
            icon={<IconClipboardEmpty />}
            title={t('tenant_admin_branches_empty_title')}
            subtitle={t('tenant_admin_branches_empty_subtitle')}
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('th_name')}</th>
                  <th>{t('field_address')}</th>
                  <th>{t('status_label')}</th>
                </tr>
              </thead>
              <tbody>
                {branches.map((b) => (
                  <tr key={b.id} className="clickable" onClick={() => setSelected(b)}>
                    <td>{b.name}</td>
                    <td className="wrap">{b.address}</td>
                    <td>
                      <span className={`status-badge ${b.is_active ? 'active' : 'inactive'}`}>
                        {activeStatusLabel(language, b.is_active ? 'active' : 'inactive')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <form onSubmit={handleCreate} style={{ marginTop: '1rem' }}>
        {error && (
          <div className="error-banner">
            <IconAlertCircle />
            <span>{error}</span>
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
        <button type="submit">
          <IconPlus />
          {t('tenant_admin_add_branch_button')}
        </button>
      </form>

      <DetailDrawer
        open={!!selected}
        title={selected?.name ?? ''}
        subtitle={t('branch_drawer_subtitle')}
        avatarLabel={selected?.name.slice(0, 2).toUpperCase()}
        onClose={() => setSelected(null)}
        footer={
          <>
            {deleteError && (
              <div className="error-banner" style={{ marginBottom: '0.9rem' }}>
                <IconAlertCircle />
                <span>{deleteError}</span>
              </div>
            )}
            <button type="button" className="danger" style={{ width: '100%' }} onClick={() => setConfirmDeleteOpen(true)}>
              <IconTrash />
              {t('branch_delete_button')}
            </button>
          </>
        }
      >
        {selected && (
          <>
            <DrawerField label={t('field_address')} value={selected.address || '—'} />
            <DrawerField
              label={t('status_label')}
              value={
                <span className={`status-badge ${selected.is_active ? 'active' : 'inactive'}`}>
                  {activeStatusLabel(language, selected.is_active ? 'active' : 'inactive')}
                </span>
              }
            />
          </>
        )}
      </DetailDrawer>

      <DoubleConfirmDialog
        open={confirmDeleteOpen}
        step1={{
          title: t('branch_delete_step1_title'),
          description: (
            <>
              <strong>{selected?.name}</strong>
              {t('branch_delete_step1_description')}
            </>
          ),
        }}
        step2={{
          title: t('delete_all_transactions_title'),
          description: (
            <>
              <strong>{selected?.name}</strong>
              {t('branch_delete_step2_description')}
            </>
          ),
        }}
        confirming={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
    </div>
  )
}

function BranchManagersSection() {
  const { t, language } = useLanguage()
  const [managers, setManagers] = useState<BranchManager[] | null>(null)
  const [branches, setBranches] = useState<Branch[] | null>(null)
  const [branchId, setBranchId] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const [selected, setSelected] = useState<BranchManager | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const loadManagers = () => {
    apiFetch<BranchManager[] | { results: BranchManager[] }>('/api/branch-managers/').then((data) =>
      setManagers(asArray(data))
    )
  }

  const handleDelete = async () => {
    if (!selected) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await apiFetch(`/api/branch-managers/${selected.id}/`, { method: 'DELETE' })
      setConfirmDeleteOpen(false)
      setSelected(null)
      loadManagers()
    } catch (err) {
      setDeleteError(err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_manager_delete_error'))
    } finally {
      setDeleting(false)
    }
  }

  useEffect(() => {
    loadManagers()
    apiFetch<Branch[] | { results: Branch[] }>('/api/branches/').then((data) => setBranches(asArray(data)))
  }, [])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await apiFetch('/api/branch-managers/', {
        method: 'POST',
        body: JSON.stringify({ branch: Number(branchId), username, password }),
      })
      setUsername('')
      setPassword('')
      loadManagers()
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_admin_manager_create_error'))
    }
  }

  if (!managers) return <SkeletonTable rows={4} />

  return (
    <div>
      <div className="table-card">
        {managers.length === 0 ? (
          <EmptyState icon={<IconUsers />} title={t('tenant_admin_managers_empty_title')} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('th_login')}</th>
                  <th>{t('field_branch')}</th>
                  <th>{t('status_label')}</th>
                </tr>
              </thead>
              <tbody>
                {managers.map((m) => (
                  <tr key={m.id} className="clickable" onClick={() => setSelected(m)}>
                    <td>{m.username}</td>
                    <td>{m.branch_name}</td>
                    <td>
                      <span className={`status-badge ${m.is_active ? 'active' : 'inactive'}`}>
                        {activeStatusLabel(language, m.is_active ? 'active' : 'inactive')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <form onSubmit={handleCreate} style={{ marginTop: '1rem' }}>
        {error && (
          <div className="error-banner">
            <IconAlertCircle />
            <span>{error}</span>
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
        <button type="submit" disabled={!branchId}>
          <IconPlus />
          {t('tenant_admin_add_manager_button')}
        </button>
      </form>

      <DetailDrawer
        open={!!selected}
        title={selected?.username ?? ''}
        subtitle={t('manager_drawer_subtitle')}
        avatarLabel={selected?.username.slice(0, 2).toUpperCase()}
        onClose={() => setSelected(null)}
        footer={
          <>
            {deleteError && (
              <div className="error-banner" style={{ marginBottom: '0.9rem' }}>
                <IconAlertCircle />
                <span>{deleteError}</span>
              </div>
            )}
            <button type="button" className="danger" style={{ width: '100%' }} onClick={() => setConfirmDeleteOpen(true)}>
              <IconTrash />
              {t('manager_delete_button')}
            </button>
          </>
        }
      >
        {selected && (
          <>
            <DrawerField label={t('field_login')} value={selected.username} />
            <DrawerField label={t('field_branch')} value={selected.branch_name} />
            <DrawerField
              label={t('status_label')}
              value={
                <span className={`status-badge ${selected.is_active ? 'active' : 'inactive'}`}>
                  {activeStatusLabel(language, selected.is_active ? 'active' : 'inactive')}
                </span>
              }
            />
          </>
        )}
      </DetailDrawer>

      <ConfirmDialog
        open={confirmDeleteOpen}
        title={t('manager_delete_title')}
        description={
          <>
            <strong>{selected?.username}</strong>
            {t('login_will_lose_access')}
          </>
        }
        confirmLabel={t('delete_confirm')}
        tone="danger"
        confirming={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
    </div>
  )
}

export default function TenantAdminPage() {
  const { user } = useAuth()
  const { t } = useLanguage()
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user?.tenantId) return
    apiFetch<Tenant>(`/api/tenants/${user.tenantId}/`)
      .then(setTenant)
      .catch((err) => setError(err.message))
  }, [user?.tenantId])

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error}</span>
      </div>
    )
  }
  if (!tenant) return <SkeletonTable rows={6} />

  return (
    <div>
      <span className="eyebrow">{t('eyebrow_tenant')}</span>
      <h2 style={{ marginBottom: '1.5rem' }}>{tenant.name}</h2>

      <div className="card">
        <div className="card-title-row">
          <h3>{t('tenant_admin_rate_card_heading')}</h3>
        </div>
        <RateForm tenant={tenant} onSaved={setTenant} />
      </div>

      <div className="section-head">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <IconBuilding /> {t('label_branches')}
        </h2>
      </div>
      <BranchesSection />

      <div className="section-head">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <IconUsers /> {t('section_heading_branch_managers')}
        </h2>
      </div>
      <BranchManagersSection />
    </div>
  )
}
