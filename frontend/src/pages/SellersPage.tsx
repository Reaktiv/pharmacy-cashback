import { useEffect, useState, type FormEvent } from 'react'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Seller } from '../api/types'
import { activeStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import StatCard from '../components/StatCard'
import EmptyState from '../components/EmptyState'
import { SkeletonStatGrid, SkeletonTable } from '../components/Skeleton'
import ConfirmDialog from '../components/ConfirmDialog'
import DetailDrawer, { DrawerField } from '../components/DetailDrawer'
import { IconAlertCircle, IconUsers, IconPulse, IconPlus, IconTrash } from '../components/Icons'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

export default function SellersPage() {
  const { user } = useAuth()
  const { t, language } = useLanguage()
  // Only the branch manager adds sellers now (CLAUDE.md §3) — the tenant
  // admin can still view this list for oversight, but the form below is
  // branch-manager-only, always scoped to their own branch.
  const isBranchManager = user?.role === 'branch_manager'

  const [sellers, setSellers] = useState<Seller[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const [branchId, setBranchId] = useState<string>('')
  const [phone, setPhone] = useState('')
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const [selected, setSelected] = useState<Seller | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const loadSellers = () => {
    apiFetch<Seller[] | { results: Seller[] }>('/api/sellers/')
      .then((data) => setSellers(asArray(data)))
      .catch((err) => setError(err.message))
  }

  const handleDelete = async () => {
    if (!selected) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await apiFetch(`/api/sellers/${selected.id}/`, { method: 'DELETE' })
      setConfirmDeleteOpen(false)
      setSelected(null)
      loadSellers()
    } catch (err) {
      setDeleteError(err instanceof ApiError ? JSON.stringify(err.data) : t('sellers_delete_error'))
    } finally {
      setDeleting(false)
    }
  }

  useEffect(() => {
    loadSellers()
    if (user?.branchId) {
      setBranchId(String(user.branchId))
    }
  }, [user?.branchId])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    try {
      await apiFetch('/api/sellers/', {
        method: 'POST',
        body: JSON.stringify({
          branch: Number(branchId),
          phone,
          full_name: fullName,
          username,
          password,
        }),
      })
      setPhone('')
      setFullName('')
      setUsername('')
      setPassword('')
      loadSellers()
    } catch (err) {
      setFormError(err instanceof ApiError ? JSON.stringify(err.data) : t('sellers_create_error'))
    }
  }

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error}</span>
      </div>
    )
  }
  if (!sellers) {
    return (
      <div>
        <SkeletonStatGrid count={2} />
        <SkeletonTable rows={6} />
      </div>
    )
  }

  const activeCount = sellers.filter((s) => s.is_active).length

  return (
    <div>
      <div className="stat-grid">
        <StatCard icon={<IconUsers />} label={t('sellers_stat_total')} value={sellers.length} />
        <StatCard
          icon={<IconPulse />}
          label={t('sellers_stat_active')}
          value={activeCount}
          tone="success"
          sub={t('sellers_stat_inactive_sub', { count: sellers.length - activeCount })}
        />
      </div>

      <div className="section-head" style={{ marginTop: 0 }}>
        <h2>{t('sellers_heading')}</h2>
      </div>
      <div className="table-card">
        {sellers.length === 0 ? (
          <EmptyState icon={<IconUsers />} title={t('sellers_empty_title')} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('th_full_name')}</th>
                  <th>{t('th_phone')}</th>
                  <th>{t('th_daily_limit')}</th>
                  <th>{t('status_label')}</th>
                </tr>
              </thead>
              <tbody>
                {sellers.map((s) => (
                  <tr key={s.id} className="clickable" onClick={() => setSelected(s)}>
                    <td>{s.full_name}</td>
                    <td>{s.phone}</td>
                    <td className="num">{s.daily_txn_limit ?? '—'}</td>
                    <td>
                      <span className={`status-badge ${s.is_active ? 'active' : 'inactive'}`}>
                        {activeStatusLabel(language, s.is_active ? 'active' : 'inactive')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {isBranchManager && (
        <>
          <div className="section-head">
            <h2>{t('sellers_add_heading')}</h2>
          </div>
          <div className="panel">
            <form onSubmit={handleCreate}>
              {formError && (
                <div className="error-banner">
                  <IconAlertCircle />
                  <span>{formError}</span>
                </div>
              )}
              <div className="form-grid">
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
              </div>
              <button type="submit" disabled={!branchId}>
                <IconPlus />
                {t('sellers_add_heading')}
              </button>
            </form>
          </div>
        </>
      )}

      <DetailDrawer
        open={!!selected}
        title={selected?.full_name ?? ''}
        subtitle={t('seller_drawer_subtitle')}
        avatarLabel={selected?.full_name.slice(0, 2).toUpperCase()}
        onClose={() => setSelected(null)}
        footer={
          isBranchManager ? (
            <>
              {deleteError && (
                <div className="error-banner" style={{ marginBottom: '0.9rem' }}>
                  <IconAlertCircle />
                  <span>{deleteError}</span>
                </div>
              )}
              <button type="button" className="danger" style={{ width: '100%' }} onClick={() => setConfirmDeleteOpen(true)}>
                <IconTrash />
                {t('seller_delete_button')}
              </button>
            </>
          ) : undefined
        }
      >
        {selected && (
          <>
            <DrawerField label={t('field_phone')} value={selected.phone} />
            <DrawerField label={t('th_daily_limit')} value={selected.daily_txn_limit ?? t('unlimited')} />
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
        title={t('seller_delete_title')}
        description={
          <>
            <strong>{selected?.full_name}</strong>
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
