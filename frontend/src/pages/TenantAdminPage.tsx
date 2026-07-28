import { useEffect, useState, type FormEvent } from 'react'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Branch, Tenant } from '../api/types'

function RateForm({ tenant, onSaved }: { tenant: Tenant; onSaved: (t: Tenant) => void }) {
  const [rate, setRate] = useState(tenant.cashback_rate)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSaved(false)
    setSubmitting(true)
    try {
      const updated = await apiFetch<Tenant>(`/api/tenants/${tenant.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ cashback_rate: rate }),
      })
      onSaved(updated)
      setSaved(true)
    } catch (err) {
      setError(
        err instanceof ApiError
          ? JSON.stringify(err.data)
          : 'Failed to update rate.'
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {error && <div className="error-banner">{error}</div>}
      {saved && <div className="success-banner">Rate updated.</div>}
      <div className="field">
        <label htmlFor="rate">Cashback rate (%)</label>
        <input
          id="rate"
          type="number"
          step="0.01"
          min="0"
          value={rate}
          onChange={(e) => setRate(e.target.value)}
        />
      </div>
      <button type="submit" disabled={submitting}>
        {submitting ? 'Saving…' : 'Save rate'}
      </button>
    </form>
  )
}

function BranchesSection() {
  const [branches, setBranches] = useState<Branch[] | null>(null)
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    apiFetch<Branch[] | { results: Branch[] }>('/api/branches/').then((data) =>
      setBranches(Array.isArray(data) ? data : data.results)
    )
  }

  useEffect(load, [])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await apiFetch('/api/branches/', {
        method: 'POST',
        body: JSON.stringify({ name, address }),
      })
      setName('')
      setAddress('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : 'Failed to create branch.')
    }
  }

  if (!branches) return <p>Loading branches…</p>

  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Address</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {branches.map((b) => (
            <tr key={b.id}>
              <td>{b.name}</td>
              <td>{b.address}</td>
              <td>
                <span className={`status-badge ${b.is_active ? 'active' : 'inactive'}`}>
                  {b.is_active ? 'active' : 'inactive'}
                </span>
              </td>
            </tr>
          ))}
          {branches.length === 0 && (
            <tr>
              <td colSpan={3} style={{ color: 'var(--text-muted)' }}>
                No branches yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <form onSubmit={handleCreate} style={{ marginTop: '1rem' }}>
        {error && <div className="error-banner">{error}</div>}
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
          <div className="field">
            <label htmlFor="branch-name">New branch name</label>
            <input id="branch-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="branch-address">Address</label>
            <input
              id="branch-address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
            />
          </div>
          <button type="submit" style={{ marginBottom: '0.75rem' }}>
            Add branch
          </button>
        </div>
      </form>
    </div>
  )
}

export default function TenantAdminPage() {
  const { user } = useAuth()
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user?.tenantId) return
    apiFetch<Tenant>(`/api/tenants/${user.tenantId}/`)
      .then(setTenant)
      .catch((err) => setError(err.message))
  }, [user?.tenantId])

  if (error) return <div className="error-banner">{error}</div>
  if (!tenant) return <p>Loading…</p>

  return (
    <div>
      <h2>{tenant.name}</h2>

      <div className="card">
        <h2>Rate setting</h2>
        <RateForm tenant={tenant} onSaved={setTenant} />
      </div>

      <h2>Branches</h2>
      <BranchesSection />
    </div>
  )
}
