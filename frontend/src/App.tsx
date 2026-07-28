import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import RoleRedirect from './pages/RoleRedirect'
import DashboardPage from './pages/DashboardPage'
import TenantDetailPage from './pages/TenantDetailPage'
import TenantAdminPage from './pages/TenantAdminPage'
import SellersPage from './pages/SellersPage'
import BroadcastsPage from './pages/BroadcastsPage'
import ReportsPage from './pages/ReportsPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/" element={<RoleRedirect />} />

              <Route element={<ProtectedRoute allow={['superadmin']} />}>
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/tenants/:id" element={<TenantDetailPage />} />
              </Route>

              <Route element={<ProtectedRoute allow={['tenant_admin']} />}>
                <Route path="/tenant" element={<TenantAdminPage />} />
                <Route path="/broadcasts" element={<BroadcastsPage />} />
              </Route>

              <Route
                element={<ProtectedRoute allow={['tenant_admin', 'branch_manager']} />}
              >
                <Route path="/sellers" element={<SellersPage />} />
                <Route path="/reports" element={<ReportsPage />} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
