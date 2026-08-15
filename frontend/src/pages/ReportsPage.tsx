import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
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
import { weekOverWeekTrend } from '../lib/trend'
import PageHeader from '../components/PageHeader'
import StatCard, { TrendBadge } from '../components/StatCard'
import SellerPerformanceCard from '../components/SellerPerformanceCard'
import BranchPerformanceCard from '../components/BranchPerformanceCard'
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
  IconReceipt,
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

  const {
    data,
    error,
    isPending,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['reports', 'seller-transactions', sellerId],
    queryFn: ({ pageParam }) =>
      apiFetch<SellerTransactionsPage>(
        `/api/reports/seller-transactions/?seller_id=${sellerId}&limit=${SELLER_HISTORY_PAGE_SIZE}&offset=${pageParam}`,
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.results.length, 0)
      return loaded < lastPage.count ? loaded : undefined
    },
  })

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error.message}</span>
      </div>
    )
  }

  if (isPending) return <SkeletonTable rows={4} />

  const txns = data.pages.flatMap((p) => p.results)
  const totals = data.pages[0].totals
  if (txns.length === 0) {
    return <EmptyState icon={<IconClipboardEmpty />} title={t('reports_seller_empty_title')} />
  }

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

      {hasNextPage && (
        <button
          type="button"
          className="secondary"
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
          style={{ marginTop: '0.75rem' }}
        >
          {isFetchingNextPage ? t('reports_loading_more') : t('reports_load_more')}
        </button>
      )}

      <div className="chart-card" style={{ marginTop: '1.25rem', marginBottom: 0 }}>
        <h3 style={{ marginBottom: '1rem' }}>{t('reports_overall_stats_heading')}</h3>
        <PieChart
          data={[
            { label: t('reports_pie_total_sales'), value: totals.check_amount, color: 'var(--chart-sales)' },
            { label: t('reports_pie_cashback_given'), value: totals.cashback_earned, color: 'var(--chart-earn)' },
            { label: t('reports_pie_cashback_used'), value: totals.cashback_spent, color: 'var(--chart-spend)' },
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

  // Three independent queries rather than one Promise.all: branches/daily
  // only apply to tenant_admin (enabled: canSeeBranchAndDaily), and a
  // branch_manager revisiting this page after Dashboard/Sellers now reuses
  // the cached sellers report instead of re-running the aggregation. No
  // mutations happen anywhere on this page, so — unlike Dashboard/
  // TenantDetail — there's nothing here that needs to invalidate anything.
  const sellersQuery = useQuery({
    queryKey: ['reports', 'sellers'],
    queryFn: () => apiFetch<SellerReportRow[]>('/api/reports/sellers/'),
  })
  const branchesQuery = useQuery({
    queryKey: ['reports', 'branches'],
    queryFn: () => apiFetch<BranchReportRow[]>('/api/reports/branches/'),
    enabled: canSeeBranchAndDaily,
  })
  const dailyQuery = useQuery({
    queryKey: ['reports', 'daily'],
    queryFn: () => apiFetch<DailyReportRow[]>('/api/reports/daily/?days=30'),
    enabled: canSeeBranchAndDaily,
  })

  const [expandedSellerId, setExpandedSellerId] = useState<number | null>(null)

  const error = sellersQuery.error ?? branchesQuery.error ?? dailyQuery.error

  if (error) {
    return (
      <div className="error-banner">
        <IconAlertCircle />
        <span>{error.message}</span>
      </div>
    )
  }

  const stillLoading =
    sellersQuery.isPending || (canSeeBranchAndDaily && (branchesQuery.isPending || dailyQuery.isPending))

  if (stillLoading) {
    return (
      <div>
        <SkeletonStatGrid count={4} />
        <SkeletonTable rows={8} />
      </div>
    )
  }

  const sellers = sellersQuery.data!
  const branches = branchesQuery.data ?? null
  const daily = dailyQuery.data ?? null

  const totalEarned = (branches ?? []).reduce((sum, b) => sum + b.total_earned, 0)
  const totalSpent = (branches ?? []).reduce((sum, b) => sum + b.total_spent, 0)
  const totalOutstanding = (branches ?? []).reduce((sum, b) => sum + b.outstanding, 0)
  const flaggedTotal = sellers!.reduce((sum, s) => sum + s.flagged_count, 0)

  const earnedTrend = daily ? weekOverWeekTrend(daily, 'total_earned') : null
  const spentTrend = daily ? weekOverWeekTrend(daily, 'total_spent') : null

  // branch_manager only sees their own sellers — no branch/daily data, so
  // the overview row is built from what *is* available instead of being
  // skipped entirely.
  const sellerCount = sellers!.length
  const totalTxns = sellers!.reduce((sum, s) => sum + s.txn_count, 0)
  const blendedAvgCheck = totalTxns > 0 ? sellers!.reduce((sum, s) => sum + s.avg_check * s.txn_count, 0) / totalTxns : 0

  const rankedSellers = [...sellers!].sort((a, b) => b.txn_count - a.txn_count)
  const maxTxnCount = Math.max(1, ...rankedSellers.map((s) => s.txn_count))

  return (
    <div>
      <PageHeader
        eyebrow={t('eyebrow_reports')}
        title={t('page_title_reports')}
        description={t('reports_page_description')}
      />

      <div className="stat-grid">
        {canSeeBranchAndDaily ? (
          <>
            <StatCard
              icon={<IconTrendUp />}
              label={t('label_earned')}
              value={totalEarned.toLocaleString()}
              sub={t('sub_som_total')}
              trend={earnedTrend ?? undefined}
            />
            <StatCard
              icon={<IconTrendDown />}
              label={t('label_spent')}
              value={totalSpent.toLocaleString()}
              tone="warning"
              sub={t('sub_som_total')}
              trend={spentTrend ?? undefined}
            />
            <StatCard
              icon={<IconScale />}
              label={t('label_outstanding')}
              value={totalOutstanding.toLocaleString()}
              tone="success"
              sub={t('sub_som')}
            />
            <StatCard
              icon={<IconUsers />}
              label={t('reports_stat_flagged')}
              value={flaggedTotal}
              tone={flaggedTotal > 0 ? 'warning' : 'primary'}
              sub={t('reports_stat_flagged_sub')}
            />
          </>
        ) : (
          <>
            <StatCard icon={<IconUsers />} label={t('reports_stat_seller_count')} value={sellerCount} />
            <StatCard icon={<IconReceipt />} label={t('reports_stat_total_txns')} value={totalTxns.toLocaleString()} tone="teal" />
            <StatCard
              icon={<IconScale />}
              label={t('reports_stat_avg_check')}
              value={Math.round(blendedAvgCheck).toLocaleString()}
              sub={t('sub_som')}
            />
            <StatCard
              icon={<IconAlertCircle />}
              label={t('reports_stat_flagged')}
              value={flaggedTotal}
              tone={flaggedTotal > 0 ? 'warning' : 'primary'}
              sub={t('reports_stat_flagged_sub')}
            />
          </>
        )}
      </div>

      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h2>{t('reports_sellers_heading')}</h2>
          <p>{t('reports_sellers_description')}</p>
        </div>
      </div>

      {rankedSellers.length === 0 ? (
        <EmptyState icon={<IconClipboardEmpty />} title={t('empty_no_transactions_yet')} />
      ) : (
        <div className="perf-list">
          {rankedSellers.map((row, i) => {
            const isExpandable = row.seller_id !== null
            const isExpanded = isExpandable && expandedSellerId === row.seller_id
            return (
              <SellerPerformanceCard
                key={row.seller_id ?? row.seller_name}
                rank={i + 1}
                name={row.seller_name}
                txnCount={row.txn_count}
                avgCheck={row.avg_check}
                flaggedCount={row.flagged_count}
                activityRatio={row.txn_count / maxTxnCount}
                labels={{ transactions: t('th_transactions'), avgCheck: t('th_average_check'), flagged: t('th_flagged') }}
                expandable={isExpandable}
                expanded={!!isExpanded}
                onToggle={() => setExpandedSellerId(isExpanded ? null : row.seller_id)}
              >
                {isExpandable && <SellerHistoryPanel sellerId={row.seller_id!} />}
              </SellerPerformanceCard>
            )
          })}
        </div>
      )}

      {canSeeBranchAndDaily && (
        <>
          <div className="section-head">
            <h2>{t('reports_branch_performance_heading')}</h2>
          </div>
          {branches!.length === 0 ? (
            <EmptyState icon={<IconClipboardEmpty />} title={t('empty_no_transactions_yet')} />
          ) : (
            <div className="perf-grid">
              {branches!.map((row) => (
                <BranchPerformanceCard
                  key={row.branch_id ?? row.branch_name}
                  name={row.branch_name}
                  earned={row.total_earned}
                  spent={row.total_spent}
                  outstanding={row.outstanding}
                  labels={{ earned: t('label_earned'), spent: t('label_spent'), outstanding: t('label_outstanding') }}
                />
              ))}
            </div>
          )}

          <div className="section-head">
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              {t('reports_trend_heading')}
              {earnedTrend && <TrendBadge direction={earnedTrend.direction} text={`${t('label_earned')} ${earnedTrend.text}`} />}
            </h2>
            <p>{t('last_30_days')}</p>
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
