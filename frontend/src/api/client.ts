const ACCESS_KEY = 'pharmacy_cashback_access'
const REFRESH_KEY = 'pharmacy_cashback_refresh'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, data: unknown) {
    const message =
      typeof data === 'object' && data !== null && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : `Request failed with status ${status}`
    super(message)
    this.status = status
    this.data = data
  }
}

async function refreshAccessToken(): Promise<string> {
  const refresh = getRefreshToken()
  if (!refresh) throw new ApiError(401, { detail: 'Not logged in' })

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
  localStorage.setItem(ACCESS_KEY, data.access)
  return data.access
}

/** Thin fetch wrapper: attaches the JWT, retries once through a refresh on
 * a 401, and throws ApiError with the parsed response body on failure. */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const doFetch = async (token: string | null): Promise<Response> => {
    const headers = new Headers(options.headers)
    headers.set('Content-Type', 'application/json')
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
