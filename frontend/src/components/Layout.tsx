import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const NAV_BY_ROLE: Record<string, { to: string; label: string }[]> = {
  superadmin: [{ to: '/dashboard', label: 'Dashboard' }],
  tenant_admin: [
    { to: '/tenant', label: 'Tenant' },
    { to: '/sellers', label: 'Sellers' },
    { to: '/broadcasts', label: 'Broadcasts' },
    { to: '/reports', label: 'Reports' },
  ],
  branch_manager: [
    { to: '/sellers', label: 'Sellers' },
    { to: '/reports', label: 'Reports' },
  ],
}

export default function Layout() {
  const { user, logout } = useAuth()
  const links = (user?.role && NAV_BY_ROLE[user.role]) || []

  return (
    <div>
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.75rem 1.25rem',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
          <h1>Pharmacy Cashback Admin</h1>
          <nav style={{ display: 'flex', gap: '1rem' }}>
            {links.map((link) => (
              <NavLink key={link.to} to={link.to}>
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            {user?.username} ({user?.role})
          </span>
          <button type="button" className="secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main style={{ padding: '1.25rem' }}>
        <Outlet />
      </main>
    </div>
  )
}
