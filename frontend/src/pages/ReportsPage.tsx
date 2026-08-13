import { Fragment, useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type {
  BranchReportRow,
  DailyReportRow,
  SellerReportRow,
  SellerTransactionRow,
  SellerTransactionsPage,
} from '../api/types'
import { useLanguage, type TFunction } from '../lib/i18n'
import StatCard from '../components/StatCard'
import EmptyState from '../components/EmptyState'
import { SkeletonStatGrid, SkeletonTable } from '../components/Skeleton'
import { DualBarChart, PieChart } from '../components/Charts'
import {
  IconAlertCircle,
  IconTrendUp,
  IconTrendDown,
  IconScale,
  IconUsers,
  IconClipboardEmpty,
  IconChevronDown,
} from '../components/Icons'

function formatDay(day: string): string {
  const parts = day.split('-')
  return parts.length === 3 ? `${parts[2]}.${parts[1]}` : day
}

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function txnTypeLabel(row: SellerTransactionRow, t: TFunction): string {
  if (row.type === 'reversal') return t('txn_type_reversal')
  if (row.no_cashback) return t('txn_type_no_cashback')
  if (row.cashback_spent > 0 && row.cashback_earned > 0) return t('txn_type_earn_and_spend')
  if (row.cashback_spent > 0) return t('txn_type_spend')
  return t('txn_type_sale')
}

const SELLER_HISTORY_PAGE_SIZE = 100

function SellerHistoryPanel({ sellerId }: { sellerId: number }) {
  const { t } = useLanguage()
  const [page, setPage] = useState<SellerTransactionsPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    setPage(null)
    setError(null)
    apiFetch<SellerTransactionsPage>(
      `/api/reports/seller-transactions/?seller_id=${sellerId}&limit=${SELLER_HISTORY_PAGE_SIZE}`
    )
      .then(setPage)
      .catch((err) => setError(err.message))
  }, [sellerId])

  const loadMore = () => {
    if (!page || loadingMore) return
    setLoadingMore(true)
    apiFetch<SellerTransactionsPage>(
      `/api/reports/seller-transactions/?seller_id=${sellerId}&limit=${SELLER_HISTORY_PAGE_SIZE}&offset=${page.results.length}`
    )
      .then((next) => setPage({ ...next, results: [...page.results, ...next.results] }))
      .catch((err) => setError(err.message))
      .finally(() => setLoadingMore(false))
  }

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error}</span>
      </div>
    )
  }

  if (!page) return <SkeletonTable rows={4} />

  const txns = page.results

  if (txns.length === 0) {
    return <EmptyState icon={<IconClipboardEmpty />} title={t('reports_seller_empty_title')} />
  }

  // Totals come from the server and cover the seller's full history, not
  // just the transactions currently loaded on the page below.
  const totalSales = page.totals.check_amount
  const totalEarned = page.totals.cashback_earned
  const totalSpent = page.totals.cashback_spent

  return (
    <div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t('th_datetime')}</th>
              <th>{t('th_customer_phone')}</th>
              <th>{t('th_check_amount')}</th>
              <th>{t('th_cash_paid')}</th>
              <th>{t('th_cashback_earned')}</th>
              <th>{t('th_cashback_spent')}</th>
              <th>{t('th_type')}</th>
            </tr>
          </thead>
          <tbody>
            {txns.map((row) => (
              <tr key={row.id}>
                <td className="num">{formatDateTime(row.created_at)}</td>
                <td>{row.customer_phone}</td>
                <td className="num">{row.check_amount.toLocaleString()}</td>
                <td className="num">{row.cash_paid.toLocaleString()}</td>
                <td className="num">{row.cashback_earned.toLocaleString()}</td>
                <td className="num">{row.cashback_spent.toLocaleString()}</td>
                <td>
                  <span className="pill">{txnTypeLabel(row, t)}</span>
                  {row.status === 'reversed' && (
                    <span className="status-badge inactive" style={{ marginLeft: '0.4rem' }}>
                      {t('status_reversed')}
                    </span>
                  )}
                  {row.flagged && (
                    <span className="status-badge inactive" style={{ marginLeft: '0.4rem' }}>
                      {t('status_flagged')}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {txns.length < page.count && (
        <button
          type="button"
          className="secondary"
          onClick={loadMore}
          disabled={loadingMore}
          style={{ marginTop: '0.75rem' }}
        >
          {loadingMore ? t('reports_loading_more') : t('reports_load_more')}
        </button>
      )}

      <div className="chart-card" style={{ marginTop: '1.25rem', marginBottom: 0 }}>
        <h3 style={{ marginBottom: '1rem' }}>{t('reports_overall_stats_heading')}</h3>
        <PieChart
          data={[
            { label: t('reports_pie_total_sales'), value: totalSales, color: 'var(--chart-sales)' },
            { label: t('reports_pie_cashback_given'), value: totalEarned, color: 'var(--chart-earn)' },
            { label: t('reports_pie_cashback_used'), value: totalSpent, color: 'var(--chart-spend)' },
          ]}
        />
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const { user } = useAuth()
  const { t } = useLanguage()
  const canSeeBranchAndDaily = user?.role === 'tenant_admin'

  const [sellers, setSellers] = useState<SellerReportRow[] | null>(null)
  const [branches, setBranches] = useState<BranchReportRow[] | null>(null)
  const [daily, setDaily] = useState<DailyReportRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedSellerId, setExpandedSellerId] = useState<number | null>(null)

  useEffect(() => {
    const requests: Promise<void>[] = [
      apiFetch<SellerReportRow[]>('/api/reports/sellers/').then(setSellers),
    ]
    if (canSeeBranchAndDaily) {
      requests.push(apiFetch<BranchReportRow[]>('/api/reports/branches/').then(setBranches))
      requests.push(apiFetch<DailyReportRow[]>('/api/reports/daily/?days=30').then(setDaily))
    }
    Promise.all(requests).catch((err) => setError(err.message))
  }, [canSeeBranchAndDaily])

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error}</span>
      </div>
    )
  }

  const stillLoading = !sellers || (canSeeBranchAndDaily && (!branches || !daily))

  if (stillLoading) {
    return (
      <div>
        <SkeletonStatGrid count={3} />
        <SkeletonTable rows={8} />
      </div>
    )
  }

  const totalEarned = (branches ?? []).reduce((sum, b) => sum + b.total_earned, 0)
  const totalSpent = (branches ?? []).reduce((sum, b) => sum + b.total_spent, 0)
  const totalOutstanding = (branches ?? []).reduce((sum, b) => sum + b.outstanding, 0)
  const flaggedTotal = sellers!.reduce((sum, s) => sum + s.flagged_count, 0)

  return (
    <div>
      {canSeeBranchAndDaily && (
        <div className="stat-grid">
          <StatCard icon={<IconTrendUp />} label={t('label_earned')} value={totalEarned.toLocaleString()} sub={t('sub_som_total')} />
          <StatCard icon={<IconTrendDown />} label={t('label_spent')} value={totalSpent.toLocaleString()} tone="warning" sub={t('sub_som_total')} />
          <StatCard icon={<IconScale />} label={t('label_outstanding')} value={totalOutstanding.toLocaleString()} tone="success" sub={t('sub_som')} />
          <StatCard icon={<IconUsers />} label={t('reports_stat_flagged')} value={flaggedTotal} tone="teal" sub={t('reports_stat_flagged_sub')} />
        </div>
      )}

      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h2>{t('reports_sellers_heading')}</h2>
          <p>{t('reports_sellers_description')}</p>
        </div>
      </div>
      <div className="table-card">
        {sellers!.length === 0 ? (
          <EmptyState icon={<IconClipboardEmpty />} title={t('empty_no_transactions_yet')} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('th_seller')}</th>
                  <th>{t('th_transactions')}</th>
                  <th>{t('th_average_check')}</th>
                  <th>{t('th_flagged')}</th>
                </tr>
              </thead>
              <tbody>
                {sellers!.map((row) => {
                  const isExpandable = row.seller_id !== null
                  const isExpanded = isExpandable && expandedSellerId === row.seller_id
                  return (
                    <Fragment key={row.seller_id ?? row.seller_name}>
                      <tr
                        className={isExpandable ? 'clickable' : undefined}
                        onClick={
                          isExpandable
                            ? () => setExpandedSellerId(isExpanded ? null : row.seller_id)
                            : undefined
                        }
                      >
                        <td>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            {isExpandable && (
                              <IconChevronDown className={`row-chevron${isExpanded ? ' expanded' : ''}`} />
                            )}
                            {row.seller_name}
                          </span>
                        </td>
                        <td className="num">{row.txn_count}</td>
                        <td className="num">{row.avg_check.toLocaleString()}</td>
                        <td className="num">{row.flagged_count}</td>
                      </tr>
                      {isExpanded && (
                        <tr className="expanded-row">
                          <td colSpan={4}>
                            <SellerHistoryPanel sellerId={row.seller_id!} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {canSeeBranchAndDaily && (
        <>
          <div className="section-head">
            <h2>{t('reports_branches_heading')}</h2>
          </div>
          <div className="table-card">
            {branches!.length === 0 ? (
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
                    {branches!.map((row) => (
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
            <h2>{t('last_30_days')}</h2>
          </div>
          <div className="chart-card">
            <DualBarChart
              data={daily!.map((d) => ({ label: formatDay(d.day), a: d.total_earned, b: d.total_spent }))}
              seriesALabel={t('label_earned')}
              seriesBLabel={t('label_spent')}
            />
          </div>
        </>
      )}
    </div>
  )
}
