import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../api/client'
import type { BranchReportRow, DailyReportRow, Tenant } from '../api/types'

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [branches, setBranches] = useState<BranchReportRow[] | null>(null)
  const [daily, setDaily] = useState<DailyReportRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    Promise.all([
      apiFetch<Tenant>(`/api/tenants/${id}/`),
      apiFetch<BranchReportRow[]>(`/api/reports/branches/?tenant_id=${id}`),
      apiFetch<DailyReportRow[]>(`/api/reports/daily/?tenant_id=${id}&days=14`),
    ])
      .then(([t, b, d]) => {
        setTenant(t)
        setBranches(b)
        setDaily(d)
      })
      .catch((err) => setError(err.message))
  }, [id])

  if (error) return <div className="error-banner">{error}</div>
  if (!tenant || !branches || !daily) return <p>Loading…</p>

  return (
    <div>
      <p>
        <Link to="/dashboard">&larr; All tenants</Link>
      </p>
      <h2>{tenant.name}</h2>
      <div className="card">
        <p>
          <strong>Slug:</strong> {tenant.slug} &nbsp;|&nbsp;
          <strong>Cashback rate:</strong> {tenant.cashback_rate}% &nbsp;|&nbsp;
          <strong>Min redeem:</strong> {tenant.min_redeem_amount} &nbsp;|&nbsp;
          <strong>Status:</strong> {tenant.is_active ? 'active' : 'inactive'}
        </p>
      </div>

      <h2>Branches</h2>
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

      <h2 style={{ marginTop: '1.5rem' }}>Last 14 days</h2>
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
    </div>
  )
}
