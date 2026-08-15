import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import type { PlatformBranding } from '../api/types'
import { IconAlertCircle, IconChevronDown } from '../components/Icons'
import { LANGUAGES, useLanguage, type Language } from '../lib/i18n'

/** Deliberately a plain, un-authenticated fetch — NOT apiFetch/
 * apiFetchObjectUrl. Those attach whatever JWT is still sitting in
 * sessionStorage (e.g. an expired one from the session that just logged the
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

/** Fallback brand mark shown on the left panel when no tenant/platform logo
 * is configured — a plain ring + monogram, drawn in white so it reads
 * against the dark-green panel. */
function DefaultBrandMark() {
  return (
    <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="44" stroke="white" strokeWidth="5" />
      <text
        x="50"
        y="63"
        textAnchor="middle"
        fontFamily="'Public Sans', sans-serif"
        fontWeight="800"
        fontSize="34"
        fill="white"
      >
        PC
      </text>
    </svg>
  )
}

function LoginLanguageSwitcher() {
  const { language, setLanguage } = useLanguage()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  return (
    <div className="lang-dropdown" ref={rootRef}>
      <button
        type="button"
        className="lang-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {language.toUpperCase()}
        <IconChevronDown className={`lang-dropdown-chevron${open ? ' open' : ''}`} />
      </button>
      {open && (
        <ul className="lang-dropdown-menu" role="listbox">
          {LANGUAGES.map((code) => (
            <li key={code}>
              <button
                type="button"
                role="option"
                aria-selected={code === language}
                className={`lang-dropdown-option${code === language ? ' active' : ''}`}
                onClick={() => {
                  setLanguage(code as Language)
                  setOpen(false)
                }}
              >
                {code.toUpperCase()}
              </button>
            </li>
          ))}
        </ul>
      )}
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
      <div className="auth-left">
        <span className="auth-left-mark" aria-hidden="true">
          {branding.logoUrl ? <img src={branding.logoUrl} alt="" /> : <DefaultBrandMark />}
        </span>
        <div className="auth-left-brand-text">
          <span className="auth-left-name">{branding.name ?? 'Pharmacy Cashback'}</span>
          <span className="auth-left-subtitle">{t('login_brand_subtitle')}</span>
        </div>
      </div>
      <div className="auth-right">
        <LoginLanguageSwitcher />
        <div className="auth-form-wrap">
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
    </div>
  )
}
