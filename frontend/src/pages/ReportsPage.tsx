import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { BranchReportRow, DailyReportRow, SellerReportRow } from '../api/types'

export default function ReportsPage() {
  const { user } = useAuth()
  const canSeeBranchAndDaily = user?.role === 'tenant_admin'

  const [sellers, setSellers] = useState<SellerReportRow[] | null>(null)
  const [branches, setBranches] = useState<BranchReportRow[] | null>(null)
  const [daily, setDaily] = useState<DailyReportRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  if (error) return <div className="error-banner">{error}</div>

  return (
    <div>
      <h2>Sellers — transaction count &amp; average check</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
        A high flagged count relative to transaction count is a fraud signal.
      </p>
      {!sellers ? (
        <p>Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Seller</th>
              <th>Transactions</th>
              <th>Avg check</th>
              <th>Flagged</th>
            </tr>
          </thead>
          <tbody>
            {sellers.map((row) => (
              <tr key={row.seller_id ?? row.seller_name}>
                <td>{row.seller_name}</td>
                <td>{row.txn_count}</td>
                <td>{row.avg_check.toLocaleString()}</td>
                <td>{row.flagged_count}</td>
              </tr>
            ))}
            {sellers.length === 0 && (
              <tr>
                <td colSpan={4} style={{ color: 'var(--text-muted)' }}>
                  No transactions yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      {canSeeBranchAndDaily && (
        <>
          <h2 style={{ marginTop: '1.5rem' }}>Branches — earned / spent / outstanding</h2>
          {!branches ? (
            <p>Loading…</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Branch</th>
                  <th>Earned</th>
                  <th>Spent</th>
                  <th>Outstanding</th>
                </tr>
              </thead>
              <tbody>
                {branches.map((row) => (
                  <tr key={row.branch_id ?? row.branch_name}>
                    <td>{row.branch_name}</td>
                    <td>{row.total_earned.toLocaleString()}</td>
                    <td>{row.total_spent.toLocaleString()}</td>
                    <td>{row.outstanding.toLocaleString()}</td>
                  </tr>
                ))}
                {branches.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ color: 'var(--text-muted)' }}>
                      No transactions yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}

          <h2 style={{ marginTop: '1.5rem' }}>Last 30 days</h2>
          {!daily ? (
            <p>Loading…</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Earned</th>
                  <th>Spent</th>
                </tr>
              </thead>
              <tbody>
                {daily.map((row) => (
                  <tr key={row.day}>
                    <td>{row.day}</td>
                    <td>{row.total_earned.toLocaleString()}</td>
                    <td>{row.total_spent.toLocaleString()}</td>
                  </tr>
                ))}
                {daily.length === 0 && (
                  <tr>
                    <td colSpan={3} style={{ color: 'var(--text-muted)' }}>
                      No activity in this range.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}
