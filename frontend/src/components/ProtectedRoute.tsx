import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { Role } from '../api/types'

export default function ProtectedRoute({ allow }: { allow?: Role[] }) {
  const { user } = useAuth()

  if (!user) return <Navigate to="/login" replace />
  if (allow && (!user.role || !allow.includes(user.role))) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}
