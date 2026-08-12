import { useEffect, useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import type { PlatformBranding } from '../api/types'
import Brand from '../components/Logo'
import { IconAlertCircle } from '../components/Icons'
import { LANGUAGES, useLanguage, type Language } from '../lib/i18n'

/** Deliberately a plain, un-authenticated fetch — NOT apiFetch/
 * apiFetchObjectUrl. Those attach whatever JWT is still sitting in
 * localStorage (e.g. an expired one from the session that just logged the
 * user out onto this very page), and SimpleJWT's authenticator raises on
 * an invalid token before DRF ever reaches the view's AllowAny permission
 * — so a stale token would 401 this "public" endpoint. Plain fetch never
 * sends the header at all, sidestepping that entirely. */
function usePlatformBranding(): { name: string | null; logoUrl: string | null } {
  const [name, setName] = useState<string | null>(null)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    fetch('/api/branding/')
      .then((res) => (res.ok ? (res.json() as Promise<PlatformBranding>) : Promise.reject()))
      .then((data) => {
        if (cancelled) return
        setName(data.name)
        if (!data.has_logo) return
        return fetch('/api/branding/logo/')
          .then((res) => (res.ok ? res.blob() : Promise.reject()))
          .then((blob) => {
            if (cancelled) return
            objectUrl = URL.createObjectURL(blob)
            setLogoUrl(objectUrl)
          })
      })
      .catch(() => {})
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [])

  return { name, logoUrl }
}

function LoginLanguageSwitcher() {
  const { language, setLanguage } = useLanguage()
  return (
    <div className="language-switcher" role="group" aria-label="Til" style={{ marginBottom: '1.25rem' }}>
      {LANGUAGES.map((code) => (
        <button
          key={code}
          type="button"
          className={`language-switcher-option${code === language ? ' active' : ''}`}
          onClick={() => setLanguage(code as Language)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}

export default function LoginPage() {
  const { user, login } = useAuth()
  const { t } = useLanguage()
  const branding = usePlatformBranding()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to="/" replace />

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('login_error_fallback'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <LoginLanguageSwitcher />
        <Brand
          subtitle={t('login_brand_subtitle')}
          name={branding.name ?? undefined}
          logoUrl={branding.logoUrl}
        />
        <h1>{t('login_heading')}</h1>
        <p className="auth-sub">{t('login_subheading')}</p>
        {error && (
          <div className="error-banner">
            <IconAlertCircle />
            <span>{error}</span>
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="field" style={{ maxWidth: 'none' }}>
            <label htmlFor="username">{t('login_username')}</label>
            <input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div className="field" style={{ maxWidth: 'none' }}>
            <label htmlFor="password">{t('login_password')}</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" disabled={submitting} style={{ width: '100%', marginTop: '0.5rem' }}>
            {submitting ? t('login_submitting') : t('login_submit')}
          </button>
        </form>
      </div>
    </div>
  )
}
