// Minimal JWT payload decoder — just base64url + JSON.parse, no signature
// verification (that's the server's job; the client only reads the
// informational claims TenantAwareTokenObtainPairSerializer embeds:
// role/tenant_id/branch_id). Avoids pulling in a jwt-decode dependency for
// something this small.
export interface AccessTokenClaims {
  user_id: number
  role: 'superadmin' | 'tenant_admin' | 'branch_manager' | 'seller' | null
  tenant_id: number | null
  branch_id: number | null
  exp: number
}

export function decodeAccessToken(token: string): AccessTokenClaims {
  const payload = token.split('.')[1]
  const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
  const json = decodeURIComponent(
    atob(base64)
      .split('')
      .map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0'))
      .join('')
  )
  return JSON.parse(json) as AccessTokenClaims
}
