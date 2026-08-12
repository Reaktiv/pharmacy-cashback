import { useEffect, useState } from 'react'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Branch, BranchManager, Tenant } from '../api/types'
import { activeStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import EmptyState from '../components/EmptyState'
import { SkeletonTable } from '../components/Skeleton'
import ConfirmDialog, { DoubleConfirmDialog } from '../components/ConfirmDialog'
import DetailDrawer, { DrawerField } from '../components/DetailDrawer'
import SellersList from '../components/SellersList'
import { IconAlertCircle, IconBuilding, IconUsers, IconClipboardEmpty, IconTrash } from '../components/Icons'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

/** Read-only branches list — creating a branch now lives on the Sozlamalar
 * (Settings) page (TenantSettingsPage's AddBranchForm), this section is
 * just for oversight + deactivating/deleting an existing one. */
function BranchesSection({ branchLimit }: { branchLimit: number | null }) {
  const { t, language } = useLanguage()
  const [branches, setBranches] = useState<Branch[] | null>(null)

  const [selected, setSelected] = useState<Branch | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const load = () => {
    apiFetch<Branch[] | { results: Branch[] }>('/api/branches/').then((data) => setBranches(asArray(data)))
  }

  useEffect(load, [])

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
      <p className="text-muted" style={{ marginTop: 0 }}>
        {t('tenant_branch_limit_usage', {
          used: branches.length,
          limit: branchLimit === null ? '∞' : branchLimit,
        })}
      </p>
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

/** Read-only branch admins list — assigning a new one now lives on the
 * Sozlamalar page (TenantSettingsPage's AddBranchManagerForm). */
function BranchManagersSection() {
  const { t, language } = useLanguage()
  const [managers, setManagers] = useState<BranchManager[] | null>(null)

  const [selected, setSelected] = useState<BranchManager | null>(null)
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const loadManagers = () => {
    apiFetch<BranchManager[] | { results: BranchManager[] }>('/api/branch-managers/').then((data) =>
      setManagers(asArray(data))
    )
  }

  useEffect(loadManagers, [])

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

/** The tenant admin's "Dorixona" overview: branches, branch admins, and
 * sellers, all read-only listings with drill-in drawers for oversight —
 * renaming the pharmacy, setting the rate, adding branches/admins all
 * moved to the separate Sozlamalar page (TenantSettingsPage). */
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

      <div className="section-head" style={{ marginTop: 0 }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <IconBuilding /> {t('label_branches')}
        </h2>
      </div>
      <BranchesSection branchLimit={tenant.branch_limit} />

      <div className="section-head">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <IconUsers /> {t('section_heading_branch_managers')}
        </h2>
      </div>
      <BranchManagersSection />

      <div className="section-head">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <IconUsers /> {t('sellers_heading')}
        </h2>
      </div>
      <SellersList canManage={false} />
    </div>
  )
}
