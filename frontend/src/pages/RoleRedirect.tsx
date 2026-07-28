import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const LANDING_BY_ROLE: Record<string, string> = {
  superadmin: '/dashboard',
  tenant_admin: '/tenant',
  branch_manager: '/sellers',
}

/** Sends a freshly-logged-in user to whichever page makes sense for their
 * role. Sellers don't have a page here at all — they use the seller-web
 * register page, not this panel (CLAUDE.md §7a: the customer bot/seller
 * flow must never expose seller actions here). */
export default function RoleRedirect() {
  const { user } = useAuth()
  if (!user?.role || !(user.role in LANDING_BY_ROLE)) {
    return (
      <div className="card">
        <h2>No panel for this role</h2>
        <p>
          {user?.role === 'seller'
            ? 'Sellers use the register page at /seller/, not this admin panel.'
            : 'Your account has no role assigned. Contact a superadmin.'}
        </p>
      </div>
    )
  }
  return <Navigate to={LANDING_BY_ROLE[user.role]} replace />
}
