import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { ApiError, clearTokens, getAccessToken, setTokens } from '../api/client'
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

  const login = async (username: string, password: string) => {
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
  }

  const logout = () => {
    clearTokens()
    sessionStorage.removeItem(USERNAME_KEY)
    setUser(null)
  }

  const value = useMemo(() => ({ user, login, logout }), [user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
