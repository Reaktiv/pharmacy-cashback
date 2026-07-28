import { useEffect, useState, type FormEvent } from 'react'
import { apiFetch, ApiError } from '../api/client'
import type { Broadcast } from '../api/types'

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

export default function BroadcastsPage() {
  const [broadcasts, setBroadcasts] = useState<Broadcast[] | null>(null)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sendingId, setSendingId] = useState<number | null>(null)

  const load = () => {
    apiFetch<Broadcast[] | { results: Broadcast[] }>('/api/broadcasts/').then((data) =>
      setBroadcasts(asArray(data))
    )
  }

  useEffect(load, [])

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await apiFetch('/api/broadcasts/', {
        method: 'POST',
        body: JSON.stringify({ title, body }),
      })
      setTitle('')
      setBody('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : 'Failed to create broadcast.')
    }
  }

  const handleSend = async (id: number) => {
    setSendingId(id)
    setError(null)
    try {
      await apiFetch(`/api/broadcasts/${id}/send/`, { method: 'POST' })
      load()
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : 'Failed to send broadcast.')
    } finally {
      setSendingId(null)
    }
  }

  if (!broadcasts) return <p>Loading…</p>

  return (
    <div>
      <h2>Broadcasts</h2>
      {error && <div className="error-banner">{error}</div>}
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Status</th>
            <th>Sent</th>
            <th>Failed</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {broadcasts.map((b) => (
            <tr key={b.id}>
              <td>{b.title}</td>
              <td>{b.status}</td>
              <td>{b.sent_count}</td>
              <td>{b.failed_count}</td>
              <td>
                {b.status === 'draft' && (
                  <button
                    type="button"
                    className="secondary"
                    disabled={sendingId === b.id}
                    onClick={() => handleSend(b.id)}
                  >
                    {sendingId === b.id ? 'Sending…' : 'Send'}
                  </button>
                )}
              </td>
            </tr>
          ))}
          {broadcasts.length === 0 && (
            <tr>
              <td colSpan={5} style={{ color: 'var(--text-muted)' }}>
                No broadcasts yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2 style={{ marginTop: '1.5rem' }}>New broadcast</h2>
      <form onSubmit={handleCreate} style={{ maxWidth: 480 }}>
        <div className="field" style={{ maxWidth: 480 }}>
          <label htmlFor="broadcast-title">Title</label>
          <input
            id="broadcast-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </div>
        <div className="field" style={{ maxWidth: 480 }}>
          <label htmlFor="broadcast-body">Message</label>
          <textarea
            id="broadcast-body"
            rows={4}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
          />
        </div>
        <button type="submit">Save as draft</button>
      </form>
    </div>
  )
}
