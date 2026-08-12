import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import type { CrossTenantDashboardRow, Tenant } from '../api/types'
import { activeStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import StatCard from '../components/StatCard'
import EmptyState from '../components/EmptyState'
import { SkeletonStatGrid, SkeletonTable } from '../components/Skeleton'
import DetailDrawer from '../components/DetailDrawer'
import { IconAlertCircle, IconBuilding, IconUsers, IconReceipt, IconWallet, IconPlus, IconClipboardEmpty } from '../components/Icons'

function NewTenantDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const { t } = useLanguage()
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [cashbackRate, setCashbackRate] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const created = await apiFetch<Tenant>('/api/tenants/', {
        method: 'POST',
        body: JSON.stringify({ name, slug, cashback_rate: cashbackRate }),
      })
      navigate(`/tenants/${created.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('dashboard_create_tenant_error'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <DetailDrawer open={open} title={t('dashboard_add_new_tenant_heading')} onClose={onClose}>
      <form onSubmit={handleCreate}>
        {error && (
          <div className="error-banner">
            <IconAlertCircle />
            <span>{error}</span>
          </div>
        )}
        <div className="field">
          <label htmlFor="tenant-name">{t('field_tenant_name')}</label>
          <input id="tenant-name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="tenant-slug">{t('field_slug')}</label>
          <input id="tenant-slug" value={slug} onChange={(e) => setSlug(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="tenant-rate">{t('field_cashback_rate')}</label>
          <input
            id="tenant-rate"
            type="number"
            step="0.01"
            min="0"
            value={cashbackRate}
            onChange={(e) => setCashbackRate(e.target.value)}
            required
          />
          <p className="hint">{t('hint_rate_format', { ten: 10, zeroTen: '0.10' })}</p>
        </div>
        <button type="submit" disabled={submitting}>
          <IconPlus />
          {submitting ? t('dashboard_creating') : t('dashboard_add_tenant_button')}
        </button>
      </form>
    </DetailDrawer>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { t, language } = useLanguage()
  const [rows, setRows] = useState<CrossTenantDashboardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [addOpen, setAddOpen] = useState(false)

  useEffect(() => {
    apiFetch<CrossTenantDashboardRow[]>('/api/reports/cross-tenant/')
      .then(setRows)
      .catch((err) => setError(err.message))
  }, [])

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error}</span>
      </div>
    )
  }

  if (!rows) {
    return (
      <div>
        <SkeletonStatGrid count={4} />
        <SkeletonTable rows={6} />
      </div>
    )
  }

  const totalCustomers = rows.reduce((sum, r) => sum + r.customers, 0)
  const totalTodayTxns = rows.reduce((sum, r) => sum + r.today_txns, 0)
  const totalLiability = rows.reduce((sum, r) => sum + r.total_liability, 0)
  const activeCount = rows.filter((r) => r.status === 'active').length

  return (
    <div>
      <div className="stat-grid">
        <StatCard
          icon={<IconBuilding />}
          label={t('dashboard_stat_total_tenants')}
          value={rows.length}
          sub={t('dashboard_stat_active_count', { count: activeCount })}
        />
        <StatCard
          icon={<IconUsers />}
          label={t('dashboard_stat_total_customers')}
          value={totalCustomers.toLocaleString()}
          tone="teal"
          sub={t('dashboard_stat_customers_sub')}
        />
        <StatCard
          icon={<IconReceipt />}
          label={t('dashboard_stat_today_txns')}
          value={totalTodayTxns.toLocaleString()}
          tone="warning"
          sub={t('dashboard_stat_today_txns_sub')}
        />
        <StatCard
          icon={<IconWallet />}
          label={t('dashboard_stat_total_liability')}
          value={totalLiability.toLocaleString()}
          tone="success"
          sub={t('dashboard_stat_liability_sub')}
        />
      </div>

      <div className="section-head">
        <div>
          <h2>{t('dashboard_all_tenants_heading')}</h2>
          <p>{t('dashboard_all_tenants_hint')}</p>
        </div>
        <button type="button" onClick={() => setAddOpen(true)}>
          <IconPlus />
          {t('dashboard_add_tenant_button')}
        </button>
      </div>

      <div className="table-card">
        {rows.length === 0 ? (
          <EmptyState
            icon={<IconClipboardEmpty />}
            title={t('dashboard_empty_title')}
            subtitle={t('dashboard_empty_subtitle')}
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('th_bot')}</th>
                  <th>{t('th_tenant')}</th>
                  <th>{t('th_customers')}</th>
                  <th>{t('th_active_30d')}</th>
                  <th>{t('th_today_txns')}</th>
                  <th>{t('th_total_liability')}</th>
                  <th>{t('th_status')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.tenant_id} className="clickable" onClick={() => navigate(`/tenants/${row.tenant_id}`)}>
                    <td>{row.bot_username ?? '—'}</td>
                    <td>{row.tenant_name}</td>
                    <td className="num">{row.customers}</td>
                    <td className="num">{row.active_30d}</td>
                    <td className="num">{row.today_txns}</td>
                    <td className="num">{row.total_liability.toLocaleString()}</td>
                    <td>
                      <span className={`status-badge ${row.status}`}>{activeStatusLabel(language, row.status)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <NewTenantDrawer open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  )
}
