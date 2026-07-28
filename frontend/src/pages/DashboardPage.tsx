import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../api/client'
import type { CrossTenantDashboardRow } from '../api/types'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<CrossTenantDashboardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<CrossTenantDashboardRow[]>('/api/reports/cross-tenant/')
      .then(setRows)
      .catch((err) => setError(err.message))
  }, [])

  if (error) return <div className="error-banner">{error}</div>
  if (!rows) return <p>Loading…</p>

  return (
    <div>
      <h2>All tenants</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
        Click a row to drill into that tenant.
      </p>
      <table>
        <thead>
          <tr>
            <th>Bot</th>
            <th>Tenant</th>
            <th>Customers</th>
            <th>Active (30d)</th>
            <th>Today's txns</th>
            <th>Total liability</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.tenant_id}
              style={{ cursor: 'pointer' }}
              onClick={() => navigate(`/tenants/${row.tenant_id}`)}
            >
              <td>{row.bot_username ?? '—'}</td>
              <td>{row.tenant_name}</td>
              <td>{row.customers}</td>
              <td>{row.active_30d}</td>
              <td>{row.today_txns}</td>
              <td>{row.total_liability.toLocaleString()}</td>
              <td>
                <span className={`status-badge ${row.status}`}>{row.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
