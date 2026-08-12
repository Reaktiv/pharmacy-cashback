import { Navigate, Outlet, useOutletContext } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { Role } from '../api/types'

export default function ProtectedRoute({ allow }: { allow?: Role[] }) {
  const { user } = useAuth()
  // A bare <Outlet/> here would start a NEW context of its own (undefined,
  // since nothing passes one to this route), shadowing whatever the outer
  // Layout route's <Outlet context={...}/> supplied — App.tsx nests a
  // role-scoped ProtectedRoute directly between Layout and every page, so
  // without forwarding here, useOutletContext() in any page (e.g.
  // TenantAdminPage reading refreshBranding) would see undefined instead.
  const outletContext = useOutletContext()

  if (!user) return <Navigate to="/login" replace />
  if (allow && (!user.role || !allow.includes(user.role))) {
    return <Navigate to="/" replace />
  }
  return <Outlet context={outletContext} />
}
