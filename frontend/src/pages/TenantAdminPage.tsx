import { useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Branch, BranchManager, Tenant } from '../api/types'
import { activeStatusLabel, roleLabel } from '../lib/labels'
import { useLanguage, type StringKey } from '../lib/i18n'
import EmptyState from '../components/EmptyState'
import { SkeletonTable } from '../components/Skeleton'
import ConfirmDialog, { DoubleConfirmDialog } from '../components/ConfirmDialog'
import DetailDrawer, { DrawerField, DrawerSpec } from '../components/DetailDrawer'
import ActiveToggle from '../components/ActiveToggle'
import SellersList from '../components/SellersList'
import PageHeader from '../components/PageHeader'
import {
  IconAlertCircle,
  IconArrowLeft,
  IconBuilding,
  IconClipboardEmpty,
  IconTrash,
  IconUsers,
} from '../components/Icons'

const asArray = <T,>(data: T[] | { results: T[] }): T[] => (Array.isArray(data) ? data : data.results)
const initials = (name: string) => name.slice(0, 2).toUpperCase()

function StatusBadge({ active }: { active: boolean }) {
  const { language } = useLanguage()
  return (
    <span className={`status-badge ${active ? 'active' : 'inactive'}`}>
      {activeStatusLabel(language, active ? 'active' : 'inactive')}
    </span>
  )
}

/** DELETE-a-resource-then-refetch plumbing, shared by the branch and
 * branch-admin oversight drawers (same three-state dance, different URL). */
function useDelete(path: string, errorKey: StringKey, onDeleted: () => void) {
  const { t } = useLanguage()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async () => {
    if (!path) return
    setPending(true)
    setError(null)
    try {
      await apiFetch(path, { method: 'DELETE' })
      onDeleted()
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t(errorKey))
    } finally {
      setPending(false)
    }
  }
  return { run, pending, error }
}

function DeleteError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="error-banner" style={{ marginBottom: '0.9rem' }}>
      <IconAlertCircle />
      <span>{message}</span>
    </div>
  )
}

function EntityRow({
  icon,
  title,
  sub,
  active,
  onClick,
}: {
  icon: ReactNode
  title: string
  sub?: string
  active: boolean
  onClick: () => void
}) {
  return (
    <div className="entity-row" onClick={onClick}>
      <span className="entity-icon">{icon}</span>
      <div className="entity-main">
        <div className="entity-title">{title}</div>
        {sub && <div className="entity-sub">{sub}</div>}
      </div>
      <span className="entity-side">
        <StatusBadge active={active} />
      </span>
    </div>
  )
}

/** Landing view: nothing but the branch list — every row drills into a
 * single branch (BranchDetail below). */
function BranchList({
  tenant,
  branches,
  onOpen,
}: {
  tenant: Tenant
  branches: Branch[] | null
  onOpen: (branch: Branch) => void
}) {
  const { t } = useLanguage()

  return (
    <>
      <PageHeader
        eyebrow={t('eyebrow_tenant')}
        title={tenant.name}
        description={
          branches
            ? t('tenant_branch_limit_usage', {
                used: branches.length,
                limit: tenant.branch_limit === null ? '∞' : tenant.branch_limit,
              })
            : undefined
        }
      />

      {!branches ? (
        <SkeletonTable rows={4} />
      ) : branches.length === 0 ? (
        <div className="table-card">
          <EmptyState
            icon={<IconClipboardEmpty />}
            title={t('tenant_admin_branches_empty_title')}
            subtitle={t('tenant_admin_branches_empty_subtitle')}
          />
        </div>
      ) : (
        <div className="entity-list">
          {branches.map((b) => (
            <EntityRow
              key={b.id}
              icon={<IconBuilding />}
              title={b.name}
              sub={b.address || undefined}
              active={b.is_active}
              onClick={() => onOpen(b)}
            />
          ))}
        </div>
      )}
    </>
  )
}

/** One branch: its admins on their own sunken slab, then its sellers.
 * Activate/delete for the branch itself moved into the "Manage" drawer. */
function BranchDetail({ branch, onBack }: { branch: Branch; onBack: () => void }) {
  const { t, language } = useLanguage()
  const queryClient = useQueryClient()

  const { data: allManagers } = useQuery({
    queryKey: ['branch-managers'],
    queryFn: () =>
      apiFetch<BranchManager[] | { results: BranchManager[] }>('/api/branch-managers/').then(asArray),
  })
  const managers = allManagers?.filter((m) => m.branch === branch.id) ?? null

  const [manageOpen, setManageOpen] = useState(false)
  const [confirmDeleteBranch, setConfirmDeleteBranch] = useState(false)
  const [selectedManager, setSelectedManager] = useState<BranchManager | null>(null)
  const [confirmDeleteManager, setConfirmDeleteManager] = useState(false)

  const refetchBranches = () => queryClient.invalidateQueries({ queryKey: ['branches'] })
  const refetchManagers = () => queryClient.invalidateQueries({ queryKey: ['branch-managers'] })

  const branchDelete = useDelete(`/api/branches/${branch.id}/`, 'tenant_admin_branch_delete_error', () => {
    refetchBranches()
    onBack()
  })
  const managerDelete = useDelete(
    selectedManager ? `/api/branch-managers/${selectedManager.id}/` : '',
    'tenant_admin_manager_delete_error',
    () => {
      setConfirmDeleteManager(false)
      setSelectedManager(null)
      refetchManagers()
    },
  )

  return (
    <>
      <button type="button" className="secondary" onClick={onBack} style={{ marginBottom: '1rem' }}>
        <IconArrowLeft /> {t('tenant_branches_back')}
      </button>

      <PageHeader
        eyebrow={t('branch_drawer_subtitle')}
        title={branch.name}
        description={branch.address || undefined}
        actions={
          <button type="button" className="secondary" onClick={() => setManageOpen(true)}>
            {t('branch_manage_button')}
          </button>
        }
      />

      <section className="branch-admins">
        <h2>
          <IconUsers /> {t('section_heading_branch_managers')}
        </h2>
        {!managers ? (
          <SkeletonTable rows={2} />
        ) : managers.length === 0 ? (
          <EmptyState icon={<IconUsers />} title={t('branch_managers_empty')} />
        ) : (
          <div className="entity-list">
            {managers.map((m) => (
              <EntityRow
                key={m.id}
                icon={<IconUsers />}
                title={m.username}
                sub={m.branch_name}
                active={m.is_active}
                onClick={() => setSelectedManager(m)}
              />
            ))}
          </div>
        )}
      </section>

      <div className="section-head">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <IconUsers /> {t('sellers_heading')}
        </h2>
      </div>
      <SellersList canManage={false} branchId={branch.id} />

      <DetailDrawer
        open={manageOpen}
        title={branch.name}
        subtitle={t('branch_drawer_subtitle')}
        avatarLabel={initials(branch.name)}
        onClose={() => setManageOpen(false)}
        footer={
          <>
            <DeleteError message={branchDelete.error} />
            <button
              type="button"
              className="danger"
              style={{ width: '100%' }}
              onClick={() => setConfirmDeleteBranch(true)}
            >
              <IconTrash />
              {t('branch_delete_button')}
            </button>
          </>
        }
      >
        <DrawerField label={t('field_address')} value={branch.address || '—'} />
        <DrawerField label={t('status_label')} value={<StatusBadge active={branch.is_active} />} />
        <ActiveToggle<Branch>
          endpoint={`/api/branches/${branch.id}/`}
          isActive={branch.is_active}
          onSaved={refetchBranches}
        />
      </DetailDrawer>

      <DoubleConfirmDialog
        open={confirmDeleteBranch}
        step1={{
          title: t('branch_delete_step1_title'),
          description: (
            <>
              <strong>{branch.name}</strong>
              {t('branch_delete_step1_description')}
            </>
          ),
        }}
        step2={{
          title: t('delete_all_transactions_title'),
          description: (
            <>
              <strong>{branch.name}</strong>
              {t('branch_delete_step2_description')}
            </>
          ),
        }}
        confirming={branchDelete.pending}
        onConfirm={branchDelete.run}
        onCancel={() => setConfirmDeleteBranch(false)}
      />

      <DetailDrawer
        open={!!selectedManager}
        title={selectedManager ? selectedManager.full_name || selectedManager.username : ''}
        subtitle={t('manager_drawer_subtitle')}
        avatarLabel={
          selectedManager ? initials(selectedManager.full_name || selectedManager.username) : undefined
        }
        onClose={() => setSelectedManager(null)}
        footer={
          <>
            <DeleteError message={managerDelete.error} />
            <button
              type="button"
              className="danger"
              style={{ width: '100%' }}
              onClick={() => setConfirmDeleteManager(true)}
            >
              <IconTrash />
              {t('manager_delete_button')}
            </button>
          </>
        }
      >
        {selectedManager && (
          <>
            <DrawerSpec
              rows={[
                { label: t('field_full_name'), value: selectedManager.full_name || '—' },
                { label: t('field_login'), value: selectedManager.username, mono: true },
                { label: t('field_phone'), value: selectedManager.phone || '—', mono: true },
                { label: t('field_role'), value: roleLabel(language, selectedManager.role) },
                { label: t('field_branch'), value: selectedManager.branch_name },
                { label: t('status_label'), value: <StatusBadge active={selectedManager.is_active} /> },
              ]}
            />
            <ActiveToggle<BranchManager>
              endpoint={`/api/branch-managers/${selectedManager.id}/`}
              isActive={selectedManager.is_active}
              onSaved={(updated) => {
                setSelectedManager(updated)
                refetchManagers()
              }}
            />
          </>
        )}
      </DetailDrawer>

      <ConfirmDialog
        open={confirmDeleteManager}
        title={t('manager_delete_title')}
        description={
          <>
            <strong>{selectedManager && (selectedManager.full_name || selectedManager.username)}</strong>
            {t('login_will_lose_access')}
          </>
        }
        confirmLabel={t('delete_confirm')}
        tone="danger"
        confirming={managerDelete.pending}
        onConfirm={managerDelete.run}
        onCancel={() => setConfirmDeleteManager(false)}
      />
    </>
  )
}

/** The tenant admin's "Dorixona" page: a plain branch list that drills
 * into one branch at a time (its admins, then its sellers). Renaming the
 * pharmacy, the rate, adding branches/admins all live on Sozlamalar. */
export default function TenantAdminPage() {
  const { user } = useAuth()
  const [openBranchId, setOpenBranchId] = useState<number | null>(null)

  const tenantQuery = useQuery({
    queryKey: ['tenant', user?.tenantId],
    queryFn: () => apiFetch<Tenant>(`/api/tenants/${user!.tenantId}/`),
    enabled: !!user?.tenantId,
  })
  const branchesQuery = useQuery({
    queryKey: ['branches'],
    queryFn: () => apiFetch<Branch[] | { results: Branch[] }>('/api/branches/').then(asArray),
  })

  if (tenantQuery.error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{tenantQuery.error.message}</span>
      </div>
    )
  }
  if (!tenantQuery.data) return <SkeletonTable rows={6} />

  const openBranch = branchesQuery.data?.find((b) => b.id === openBranchId) ?? null

  return openBranch ? (
    <BranchDetail branch={openBranch} onBack={() => setOpenBranchId(null)} />
  ) : (
    <BranchList
      tenant={tenantQuery.data}
      branches={branchesQuery.data ?? null}
      onOpen={(b) => setOpenBranchId(b.id)}
    />
  )
}
