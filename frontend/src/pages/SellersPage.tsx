import { useEffect, useState, type FormEvent } from 'react'
import { apiFetch, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Branch, Seller } from '../api/types'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

export default function SellersPage() {
  const { user } = useAuth()
  const isTenantAdmin = user?.role === 'tenant_admin'

  const [sellers, setSellers] = useState<Seller[] | null>(null)
  const [branches, setBranches] = useState<Branch[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const [branchId, setBranchId] = useState<string>('')
  const [phone, setPhone] = useState('')
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const loadSellers = () => {
    apiFetch<Seller[] | { results: Seller[] }>('/api/sellers/')
      .then((data) => setSellers(asArray(data)))
      .catch((err) => setError(err.message))
  }

  useEffect(() => {
    loadSellers()
    if (isTenantAdmin) {
      apiFetch<Branch[] | { results: Branch[] }>('/api/branches/').then((data) =>
        setBranches(asArray(data))
      )
    } else if (user?.branchId) {
      setBranchId(String(user.branchId))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTenantAdmin, user?.branchId])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setFormError(null)
    try {
      await apiFetch('/api/sellers/', {
        method: 'POST',
        body: JSON.stringify({
          branch: Number(branchId),
          phone,
          full_name: fullName,
          username,
          password,
        }),
      })
      setPhone('')
      setFullName('')
      setUsername('')
      setPassword('')
      loadSellers()
    } catch (err) {
      setFormError(err instanceof ApiError ? JSON.stringify(err.data) : 'Failed to create seller.')
    }
  }

  if (error) return <div className="error-banner">{error}</div>
  if (!sellers) return <p>Loading…</p>

  return (
    <div>
      <h2>Sellers</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Phone</th>
            <th>Daily limit</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {sellers.map((s) => (
            <tr key={s.id}>
              <td>{s.full_name}</td>
              <td>{s.phone}</td>
              <td>{s.daily_txn_limit ?? '—'}</td>
              <td>
                <span className={`status-badge ${s.is_active ? 'active' : 'inactive'}`}>
                  {s.is_active ? 'active' : 'inactive'}
                </span>
              </td>
            </tr>
          ))}
          {sellers.length === 0 && (
            <tr>
              <td colSpan={4} style={{ color: 'var(--text-muted)' }}>
                No sellers yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 style={{ marginTop: '1.5rem' }}>Add a seller</h2>
      <form onSubmit={handleCreate}>
        {formError && <div className="error-banner">{formError}</div>}
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {isTenantAdmin && (
            <div className="field">
              <label htmlFor="seller-branch">Branch</label>
              <select
                id="seller-branch"
                value={branchId}
                onChange={(e) => setBranchId(e.target.value)}
                required
              >
                <option value="" disabled>
                  Select a branch
                </option>
                {(branches ?? []).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label htmlFor="seller-name">Full name</label>
            <input
              id="seller-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="seller-phone">Phone</label>
            <input
              id="seller-phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+998901234567"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="seller-username">Login username</label>
            <input
              id="seller-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="seller-password">Login password</label>
            <input
              id="seller-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </div>
        <button type="submit" disabled={!branchId}>
          Add seller
        </button>
      </form>
    </div>
  )
}
