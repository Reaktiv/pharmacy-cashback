import { useEffect, useState } from 'react'
import { apiFetch, ApiError } from '../api/client'
import type { Seller } from '../api/types'
import { activeStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import StatCard from './StatCard'
import EmptyState from './EmptyState'
import { SkeletonStatGrid, SkeletonTable } from './Skeleton'
import ConfirmDialog from './ConfirmDialog'
import DetailDrawer, { DrawerField } from './DetailDrawer'
import { IconAlertCircle, IconUsers, IconPulse, IconTrash } from './Icons'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

/** The sellers table + stat cards, shared between the branch manager's own
 * Sellerlar page (where it can also delete) and the tenant admin's
 * read-only "Sellerlar" section on the Dorixona overview page (CLAUDE.md
 * §3 — tenant admin doesn't add sellers directly, so no delete there
 * either). `refreshToken` lets a parent force a re-fetch (e.g. after
 * creating a seller in a drawer elsewhere) by bumping the number. */
export default function SellersList({
  canManage,
  refreshToken,
}: {
  canManage: boolean
  refreshToken?: number
}) {
  const { t, language } = useLanguage()
  const [sellers, setSellers] = useState<Seller[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [selected, setSelected] = useState<Seller | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const loadSellers = () => {
    apiFetch<Seller[] | { results: Seller[] }>('/api/sellers/')
      .then((data) => setSellers(asArray(data)))
      .catch((err) => setError(err.message))
  }

  useEffect(loadSellers, [refreshToken])

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
