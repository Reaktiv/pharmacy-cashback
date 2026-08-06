import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch, ApiError } from '../api/client'
import type { BranchReportRow, DailyReportRow, Tenant, TenantBot } from '../api/types'
import { activeStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import StatCard from '../components/StatCard'
import EmptyState from '../components/EmptyState'
import { SkeletonStatGrid, SkeletonTable } from '../components/Skeleton'
import { DualBarChart } from '../components/Charts'
import ConfirmDialog, { DoubleConfirmDialog } from '../components/ConfirmDialog'
import {
  IconAlertCircle,
  IconCheckCircle,
  IconArrowLeft,
  IconBot,
  IconBuilding,
  IconTrendUp,
  IconTrendDown,
  IconScale,
  IconClipboardEmpty,
  IconTrash,
} from '../components/Icons'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

/** The bot token endpoints return DRF field errors as {token: ["message"]}
 * (see BotSerializer.validate in apps/tenants/serializers.py) — pull the
 * message out so the settings page can show it directly instead of a raw
 * JSON blob. */
function extractFieldError(err: unknown, field: string): string | null {
  if (!(err instanceof ApiError) || typeof err.data !== 'object' || err.data === null) return null
  const value = (err.data as Record<string, unknown>)[field]
  return Array.isArray(value) && typeof value[0] === 'string' ? value[0] : null
}

function formatDay(day: string): string {
  const parts = day.split('-')
  return parts.length === 3 ? `${parts[2]}.${parts[1]}` : day
}

function BotSection({ tenantId }: { tenantId: number }) {
  const { t, language } = useLanguage()
  // `undefined` = still loading, `null` = confirmed no bot for this tenant.
  const [bot, setBot] = useState<TenantBot | null | undefined>(undefined)
  const [username, setUsername] = useState('')
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [rotateConfirmOpen, setRotateConfirmOpen] = useState(false)

  const load = () => {
    apiFetch<TenantBot[] | { results: TenantBot[] }>('/api/bots/').then((data) => {
      const bots = asArray(data)
      setBot(bots.find((b) => b.tenant === tenantId) ?? null)
    })
  }

  useEffect(load, [tenantId])

  useEffect(() => {
    if (!saved) return
    const timer = setTimeout(() => setSaved(false), 3200)
    return () => clearTimeout(timer)
  }, [saved])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const created = await apiFetch<TenantBot>('/api/bots/', {
        method: 'POST',
        body: JSON.stringify({ tenant: tenantId, username, token }),
      })
      setBot(created)
      setToken('')
      setSaved(true)
    } catch (err) {
      setError(
        extractFieldError(err, 'token') ??
          (err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_detail_bot_create_error')),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const handleRotateTokenSubmit = (event: FormEvent) => {
    event.preventDefault()
    setRotateConfirmOpen(true)
  }

  const handleRotateToken = async () => {
    if (!bot) return
    setError(null)
    setSubmitting(true)
    try {
      const updated = await apiFetch<TenantBot>(`/api/bots/${bot.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ token }),
      })
      setBot(updated)
      setToken('')
      setSaved(true)
      setRotateConfirmOpen(false)
    } catch (err) {
      setError(
        extractFieldError(err, 'token') ??
          (err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_detail_token_rotate_error')),
      )
      setRotateConfirmOpen(false)
    } finally {
      setSubmitting(false)
    }
  }

  if (bot === undefined) return <SkeletonTable rows={2} />

  if (bot === null) {
    return (
      <form onSubmit={handleCreate}>
        {error && (
          <div className="error-banner">
            <IconAlertCircle />
            <span>{error}</span>
          </div>
        )}
        <p className="text-muted" style={{ marginTop: 0 }}>
          {t('tenant_detail_no_bot')}
        </p>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="bot-username">{t('field_bot_username')}</label>
            <input id="bot-username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="bot-token">{t('field_bot_token')}</label>
            <input id="bot-token" value={token} onChange={(e) => setToken(e.target.value)} required />
          </div>
        </div>
        <button type="submit" disabled={submitting}>
          {submitting ? t('saving') : t('tenant_detail_add_bot_button')}
        </button>
      </form>
    )
  }

  return (
    <div>
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
      <p style={{ marginTop: 0 }}>
        <strong>{t('tenant_detail_bot_label')}</strong> {bot.username} &nbsp;|&nbsp;
        <strong>{t('tenant_detail_status_label')}</strong>{' '}
        <span className={`status-badge ${bot.is_active ? 'active' : 'inactive'}`}>
          {activeStatusLabel(language, bot.is_active ? 'active' : 'inactive')}
        </span>
      </p>
      <form onSubmit={handleRotateTokenSubmit}>
        <div className="field wide">
          <label htmlFor="bot-token">{t('tenant_detail_rotate_token_label')}</label>
          <input
            id="bot-token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder={t('tenant_detail_new_token_placeholder')}
            required
          />
        </div>
        <button type="submit" disabled={submitting}>
          {submitting ? t('saving') : t('tenant_detail_rotate_token_label')}
        </button>
      </form>

      <ConfirmDialog
        open={rotateConfirmOpen}
        title={t('tenant_detail_rotate_confirm_title')}
        description={t('tenant_detail_rotate_confirm_description')}
        confirmLabel={t('tenant_detail_rotate_token_label')}
        tone="danger"
        confirming={submitting}
        onConfirm={handleRotateToken}
        onCancel={() => setRotateConfirmOpen(false)}
      />
    </div>
  )
}

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { t, language } = useLanguage()
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [branches, setBranches] = useState<BranchReportRow[] | null>(null)
  const [daily, setDaily] = useState<DailyReportRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const handleDelete = async () => {
    if (!tenant) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await apiFetch(`/api/tenants/${tenant.id}/`, { method: 'DELETE' })
      navigate('/dashboard')
    } catch (err) {
      setDeleteError(err instanceof ApiError ? JSON.stringify(err.data) : t('tenant_detail_delete_error'))
      setDeleting(false)
      setDeleteOpen(false)
    }
  }

  useEffect(() => {
    if (!id) return
    Promise.all([
      apiFetch<Tenant>(`/api/tenants/${id}/`),
      apiFetch<BranchReportRow[]>(`/api/reports/branches/?tenant_id=${id}`),
      apiFetch<DailyReportRow[]>(`/api/reports/daily/?tenant_id=${id}&days=14`),
    ])
      .then(([tn, b, d]) => {
        setTenant(tn)
        setBranches(b)
        setDaily(d)
      })
      .catch((err) => setError(err.message))
  }, [id])

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error}</span>
      </div>
    )
  }

  if (!tenant || !branches || !daily) {
    return (
      <div>
        <SkeletonStatGrid count={3} />
        <SkeletonTable rows={6} />
      </div>
    )
  }

  const totalEarned = branches.reduce((sum, b) => sum + b.total_earned, 0)
  const totalSpent = branches.reduce((sum, b) => sum + b.total_spent, 0)
  const totalOutstanding = branches.reduce((sum, b) => sum + b.outstanding, 0)

  return (
    <div>
      <Link to="/dashboard" className="btn secondary" style={{ display: 'inline-flex', marginBottom: '1.25rem' }}>
        <IconArrowLeft />
        {t('tenant_detail_back_link')}
      </Link>

      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <span className="eyebrow">{t('eyebrow_tenant')}</span>
          <h2 style={{ marginBottom: '0.2rem' }}>{tenant.name}</h2>
          <p>
            {t('tenant_detail_meta', {
              slug: tenant.slug,
              rate: tenant.cashback_rate,
              status: activeStatusLabel(language, tenant.is_active ? 'active' : 'inactive'),
            })}
          </p>
        </div>
        <button type="button" className="ghost danger" onClick={() => setDeleteOpen(true)}>
          <IconTrash />
          {t('tenant_detail_delete_button')}
        </button>
      </div>

      {deleteError && (
        <div className="error-banner">
          <IconAlertCircle />
          <span>{deleteError}</span>
        </div>
      )}

      <div className="stat-grid">
        <StatCard icon={<IconTrendUp />} label={t('label_earned')} value={totalEarned.toLocaleString()} sub={t('sub_som')} />
        <StatCard
          icon={<IconTrendDown />}
          label={t('label_spent')}
          value={totalSpent.toLocaleString()}
          tone="warning"
          sub={t('sub_som')}
        />
        <StatCard
          icon={<IconScale />}
          label={t('label_outstanding_liability')}
          value={totalOutstanding.toLocaleString()}
          tone="success"
          sub={t('sub_som')}
        />
        <StatCard icon={<IconBuilding />} label={t('label_branches')} value={branches.length} tone="teal" />
      </div>

      <div className="card">
        <div className="card-title-row">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <IconBot /> {t('tenant_detail_bot_card_heading')}
          </h3>
        </div>
        <BotSection tenantId={tenant.id} />
      </div>

      <div className="section-head">
        <h2>{t('label_branches')}</h2>
      </div>
      <div className="table-card">
        {branches.length === 0 ? (
          <EmptyState icon={<IconClipboardEmpty />} title={t('empty_no_transactions_yet')} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('th_branch')}</th>
                  <th>{t('label_earned')}</th>
                  <th>{t('label_spent')}</th>
                  <th>{t('label_outstanding')}</th>
                </tr>
              </thead>
              <tbody>
                {branches.map((row) => (
                  <tr key={row.branch_id ?? row.branch_name}>
                    <td>{row.branch_name}</td>
                    <td className="num">{row.total_earned.toLocaleString()}</td>
                    <td className="num">{row.total_spent.toLocaleString()}</td>
                    <td className="num">{row.outstanding.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section-head">
        <h2>{t('last_14_days')}</h2>
      </div>
      <div className="chart-card">
        <DualBarChart
          data={daily.map((d) => ({ label: formatDay(d.day), a: d.total_earned, b: d.total_spent }))}
          seriesALabel={t('label_earned')}
          seriesBLabel={t('label_spent')}
        />
      </div>

      <DoubleConfirmDialog
        open={deleteOpen}
        step1={{
          title: t('tenant_delete_step1_title'),
          description: (
            <>
              <strong>{tenant.name}</strong>
              {t('tenant_delete_step1_description')}
            </>
          ),
        }}
        step2={{
          title: t('delete_all_transactions_title'),
          description: (
            <>
              <strong>{tenant.name}</strong>
              {t('tenant_delete_step2_description')}
            </>
          ),
        }}
        confirming={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  )
}
