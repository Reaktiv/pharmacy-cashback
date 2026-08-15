import { useEffect, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '../api/client'
import type { Seller } from '../api/types'
import { activeStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import StatCard from './StatCard'
import EmptyState from './EmptyState'
import { SkeletonStatGrid, SkeletonTable } from './Skeleton'
import ConfirmDialog from './ConfirmDialog'
import DetailDrawer, { DrawerField } from './DetailDrawer'
import ActiveToggle from './ActiveToggle'
import { IconAlertCircle, IconUsers, IconPulse, IconTrash, IconCheckCircle } from './Icons'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

/** Branch manager-only inline editor for a seller's daily transaction cap
 * (CLAUDE.md §8: a fraud-mitigation limit, only the branch manager who owns
 * this seller may change it) — read-only DrawerField everywhere else, see
 * `canManage` below. */
function DailyLimitEditor({ seller, onSaved }: { seller: Seller; onSaved: (s: Seller) => void }) {
  const { t } = useLanguage()
  const [value, setValue] = useState(seller.daily_txn_limit === null ? '' : String(seller.daily_txn_limit))
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setValue(seller.daily_txn_limit === null ? '' : String(seller.daily_txn_limit))
    setError(null)
    setSaved(false)
  }, [seller.id, seller.daily_txn_limit])

  useEffect(() => {
    if (!saved) return
    const timer = setTimeout(() => setSaved(false), 3200)
    return () => clearTimeout(timer)
  }, [saved])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const updated = await apiFetch<Seller>(`/api/sellers/${seller.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          daily_txn_limit: value.trim() === '' ? null : Number(value),
        }),
      })
      onSaved(updated)
      setSaved(true)
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('seller_daily_limit_save_error'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="field">
      <label htmlFor="seller-daily-limit-edit">{t('th_daily_limit')}</label>
      <input
        id="seller-daily-limit-edit"
        type="number"
        min={0}
        step={1}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={t('unlimited')}
      />
      <p className="hint">{t('field_daily_limit_hint')}</p>
      {error && (
        <div className="error-banner" style={{ marginTop: '0.5rem' }}>
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}
      {saved && (
        <div className="toast" style={{ marginTop: '0.5rem' }}>
          <IconCheckCircle />
          {t('tenant_detail_saved_toast')}
        </div>
      )}
      <button type="submit" disabled={submitting} className="sm" style={{ marginTop: '0.6rem' }}>
        {submitting ? t('saving') : t('save')}
      </button>
    </form>
  )
}

/** The sellers table + stat cards, shared between the branch manager's own
 * Sellerlar page (where it can also delete) and the tenant admin's
 * read-only "Sellerlar" section on the Dorixona overview page (CLAUDE.md
 * §3 — tenant admin doesn't add sellers directly, so no delete there
 * either). */
export default function SellersList({ canManage }: { canManage: boolean }) {
  const { t, language } = useLanguage()
  const queryClient = useQueryClient()
  const {
    data: sellers,
    error,
    isPending,
  } = useQuery({
    queryKey: ['sellers'],
    queryFn: () => apiFetch<Seller[] | { results: Seller[] }>('/api/sellers/').then(asArray),
  })

  const [selected, setSelected] = useState<Seller | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const handleDelete = async () => {
    if (!selected) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await apiFetch(`/api/sellers/${selected.id}/`, { method: 'DELETE' })
      setConfirmDeleteOpen(false)
      setSelected(null)
      queryClient.invalidateQueries({ queryKey: ['sellers'] })
    } catch (err) {
      setDeleteError(err instanceof ApiError ? JSON.stringify(err.data) : t('sellers_delete_error'))
    } finally {
      setDeleting(false)
    }
  }

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error.message}</span>
      </div>
    )
  }
  if (isPending) {
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

      <DetailDrawer
        open={!!selected}
        title={selected?.full_name ?? ''}
        subtitle={t('seller_drawer_subtitle')}
        avatarLabel={selected?.full_name.slice(0, 2).toUpperCase()}
        onClose={() => setSelected(null)}
        footer={
          canManage ? (
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
            {canManage ? (
              <DailyLimitEditor
                seller={selected}
                onSaved={(updated) => {
                  setSelected(updated)
                  queryClient.invalidateQueries({ queryKey: ['sellers'] })
                }}
              />
            ) : (
              <DrawerField label={t('th_daily_limit')} value={selected.daily_txn_limit ?? t('unlimited')} />
            )}
            <DrawerField
              label={t('status_label')}
              value={
                <span className={`status-badge ${selected.is_active ? 'active' : 'inactive'}`}>
                  {activeStatusLabel(language, selected.is_active ? 'active' : 'inactive')}
                </span>
              }
            />
            {canManage && (
              <ActiveToggle<Seller>
                endpoint={`/api/sellers/${selected.id}/`}
                isActive={selected.is_active}
                onSaved={(updated) => {
                  setSelected(updated)
                  queryClient.invalidateQueries({ queryKey: ['sellers'] })
                }}
              />
            )}
          </>
        )}
      </DetailDrawer>

      {canManage && (
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
      )}
    </div>
  )
}
