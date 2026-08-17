import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  ApiError,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
  SESSION_EXPIRED_EVENT,
} from '../api/client'
import { decodeAccessToken } from '../api/jwt'
import type { Role } from '../api/types'

export interface AuthUser {
  username: string
  role: Role | null
  tenantId: number | null
  branchId: number | null
}

interface AuthContextValue {
  user: AuthUser | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function userFromToken(access: string, username: string): AuthUser {
  const claims = decodeAccessToken(access)
  return {
    username,
    role: claims.role,
    tenantId: claims.tenant_id,
    branchId: claims.branch_id,
  }
}

// Username isn't a JWT claim by default, so it's cached alongside the
// tokens purely for re-hydrating `user` on a page refresh. sessionStorage,
// same as the tokens themselves (api/client.ts) — keeping this in
// localStorage while the tokens moved to sessionStorage would let one tab
// display a different tab's logged-in username.
const USERNAME_KEY = 'pharmacy_cashback_username'

function loadInitialUser(): AuthUser | null {
  const access = getAccessToken()
  const username = sessionStorage.getItem(USERNAME_KEY)
  if (!access || !username) return null
  try {
    return userFromToken(access, username)
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(loadInitialUser)
  const queryClient = useQueryClient()

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await fetch('/api/auth/token/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new ApiError(response.status, data)
      }
      const data = (await response.json()) as { access: string; refresh: string }
      setTokens(data.access, data.refresh)
      sessionStorage.setItem(USERNAME_KEY, username)
      setUser(userFromToken(data.access, username))
    },
    // No queryClient.clear() needed here: login() is only ever reachable
    // with an empty cache. LoginPage redirects away immediately whenever
    // `user` is truthy (see its `if (user) return <Navigate>` guard), so
    // this form can't be submitted while already authenticated — every
    // path into login() has either come through logout() (cache already
    // cleared there) or a fresh tab (cache never populated).
    [],
  )

  const logout = useCallback(() => {
    // Best-effort, fire-and-forget: revoke the refresh token server-side
    // (audit finding H-3) so "logout" actually ends the session instead of
    // just forgetting it in this tab — a captured refresh token would
    // otherwise keep working for up to 24h after the user thought they'd
    // logged out. Read the tokens before clearTokens() wipes them; not
    // awaited, since the UI should sign the user out immediately regardless
    // of whether this network call succeeds (e.g. offline) — the access
    // token, if still valid, will simply expire on its own at worst, and if
    // it's already dead (the SESSION_EXPIRED_EVENT path below), there's
    // nothing left to revoke anyway.
    const accessToken = getAccessToken()
    const refreshToken = getRefreshToken()
    if (accessToken && refreshToken) {
      fetch('/api/auth/token/logout/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ refresh: refreshToken }),
      }).catch(() => {
        // Nothing actionable client-side if this fails — the user is being
        // signed out of this tab either way.
      })
    }

    clearTokens()
    sessionStorage.removeItem(USERNAME_KEY)
    // The single point every session-ending path funnels through — the
    // "Chiqish" button (Layout.tsx's ConfirmDialog onConfirm={logout}) and
    // the SESSION_EXPIRED_EVENT listener below (a silently-expired refresh
    // token). Clearing the whole cache here, not just ['me'], means every
    // future useQuery migration (Dashboard, Reports, Sellers, ...) is
    // automatically covered by this same session boundary without needing
    // its own cleanup logic. Matches the "one tab = one identity" invariant
    // sessionStorage already enforces for the tokens themselves (see
    // api/client.ts).
    queryClient.clear()
    setUser(null)
  }, [queryClient])

  // api/client.ts is a plain module — when a refresh token turns out to be
  // dead mid-request, it can clear sessionStorage but has no way to reach
  // this component's state. It dispatches SESSION_EXPIRED_EVENT instead;
  // without this listener, `user` would stay truthy forever after a
  // refresh failure (nothing else ever sets it to null), so ProtectedRoute
  // never redirects and the page just hangs with every request 401ing.
  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, logout)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, logout)
  }, [logout])

  const value = useMemo(() => ({ user, login, logout }), [user, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
