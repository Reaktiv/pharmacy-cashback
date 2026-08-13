import { getStoredLanguage, translate } from '../lib/i18n'

const ACCESS_KEY = 'pharmacy_cashback_access'
const REFRESH_KEY = 'pharmacy_cashback_refresh'

// sessionStorage, not localStorage: this is a multi-tenant admin tool where
// the same person plausibly has more than one account open at once (e.g. a
// superadmin tab alongside a tenant_admin tab, or two different tenants'
// admin logins side by side). localStorage is shared across every tab of
// the same browser, so a login/refresh in one tab silently overwrote the
// token another tab was using — a request from tab A could execute under
// tab B's identity, surfacing as confusing tenant-scoped 400s/404s that
// looked like backend bugs but weren't. sessionStorage is isolated per tab,
// which eliminates that class of bug outright — the tradeoff is a brand
// new tab always starts logged out, which is the right default here.
export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string): void {
  sessionStorage.setItem(ACCESS_KEY, access)
  sessionStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
}

export class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, data: unknown) {
    const message =
      typeof data === 'object' && data !== null && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : translate(getStoredLanguage(), 'api_request_failed', { status })
    super(message)
    this.status = status
    this.data = data
  }
}

async function refreshAccessToken(): Promise<string> {
  const refresh = getRefreshToken()
  if (!refresh) throw new ApiError(401, { detail: translate(getStoredLanguage(), 'api_not_logged_in') })

  const response = await fetch('/api/auth/token/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  if (!response.ok) {
    clearTokens()
    throw new ApiError(response.status, await response.json().catch(() => ({})))
  }
  const data = (await response.json()) as { access: string }
  sessionStorage.setItem(ACCESS_KEY, data.access)
  return data.access
}

/** Thin fetch wrapper: attaches the JWT, retries once through a refresh on
 * a 401, and throws ApiError with the parsed response body on failure.
 * When `options.body` is FormData (a file upload), the browser sets its own
 * multipart Content-Type with the right boundary — forcing
 * `application/json` here would break that upload. */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const doFetch = async (token: string | null): Promise<Response> => {
    const headers = new Headers(options.headers)
    if (!(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json')
    }
    if (token) headers.set('Authorization', `Bearer ${token}`)
    return fetch(path, { ...options, headers })
  }

  let response = await doFetch(getAccessToken())

  if (response.status === 401 && getRefreshToken()) {
    const newAccess = await refreshAccessToken()
    response = await doFetch(newAccess)
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(response.status, data)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Same auth/refresh handling as apiFetch, but returns an object URL for a
 * binary response (broadcast media previews/thumbnails) instead of parsing
 * JSON. Caller owns revoking the URL via URL.revokeObjectURL when done. */
export async function apiFetchObjectUrl(path: string): Promise<string> {
  const doFetch = async (token: string | null): Promise<Response> => {
    const headers = new Headers()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    return fetch(path, { headers })
  }

  let response = await doFetch(getAccessToken())

  if (response.status === 401 && getRefreshToken()) {
    const newAccess = await refreshAccessToken()
    response = await doFetch(newAccess)
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new ApiError(response.status, data)
  }
  const blob = await response.blob()
  return URL.createObjectURL(blob)
}
