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

// This module is plain JS, not a hook/component — it has no way to call
// setUser(null) or queryClient.clear() directly when a refresh token turns
// out to be dead. AuthProvider listens for this on `window` and runs the
// same logout() it uses for the button, so a silently-expired session ends
// up in the identical state as an explicit one (ProtectedRoute redirect,
// cache cleared) instead of leaving `user` stuck truthy while every
// request 401s — see AuthContext.tsx for the listener.
export const SESSION_EXPIRED_EVENT = 'pharmacy-cashback:session-expired'

function endSession(): void {
  clearTokens()
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
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

// The backend rotates refresh tokens on every use (SIMPLE_JWT
// ROTATE_REFRESH_TOKENS=True) — each call to /api/auth/token/refresh/
// both consumes the current refresh token and returns a new one. Two
// concurrent 401s (e.g. a page firing several queries at once) used to
// each call refreshAccessToken() independently: the first to land would
// rotate in a new refresh token, and the second — already holding the
// now-superseded one in its closure — would refresh with a stale token
// and force a full logout, even though the session was perfectly valid
// moments earlier. Sharing one in-flight promise makes every concurrent
// 401 await the *same* refresh instead of racing separate ones.
let inFlightRefresh: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  if (inFlightRefresh) return inFlightRefresh

  const doRefresh = async (): Promise<string> => {
    const refresh = getRefreshToken()
    if (!refresh) {
      endSession()
      throw new ApiError(401, { detail: translate(getStoredLanguage(), 'api_not_logged_in') })
    }

    const response = await fetch('/api/auth/token/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
    if (!response.ok) {
      endSession()
      throw new ApiError(response.status, await response.json().catch(() => ({})))
    }
    // ROTATE_REFRESH_TOKENS means this response carries a new refresh
    // token too, not just a new access token — persisting only the access
    // token would leave the now-superseded refresh token stored, ready to
    // fail the *next* refresh once anything (e.g. the JWT-revocation work
    // tracked for H-3) starts actually enforcing single-use rotation.
    const data = (await response.json()) as { access: string; refresh?: string }
    sessionStorage.setItem(ACCESS_KEY, data.access)
    if (data.refresh) sessionStorage.setItem(REFRESH_KEY, data.refresh)
    return data.access
  }

  inFlightRefresh = doRefresh().finally(() => {
    inFlightRefresh = null
  })
  return inFlightRefresh
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
