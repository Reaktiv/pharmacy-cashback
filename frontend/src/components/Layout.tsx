import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { roleLabel } from '../lib/labels'
import { LANGUAGES, useLanguage, type Language, type StringKey } from '../lib/i18n'
import Brand from './Logo'
import ConfirmDialog from './ConfirmDialog'
import { IconGrid, IconBuilding, IconUsers, IconMegaphone, IconChartBar, IconLogout } from './Icons'
import type { ReactNode } from 'react'

const NAV_BY_ROLE: Record<string, { to: string; labelKey: StringKey; icon: ReactNode }[]> = {
  superadmin: [
    { to: '/dashboard', labelKey: 'nav_dashboard', icon: <IconGrid /> },
    { to: '/platform-broadcasts', labelKey: 'nav_platform_broadcasts', icon: <IconMegaphone /> },
  ],
  tenant_admin: [
    { to: '/tenant', labelKey: 'nav_tenant', icon: <IconBuilding /> },
    { to: '/sellers', labelKey: 'nav_sellers', icon: <IconUsers /> },
    { to: '/broadcasts', labelKey: 'nav_broadcasts', icon: <IconMegaphone /> },
    { to: '/reports', labelKey: 'nav_reports', icon: <IconChartBar /> },
  ],
  branch_manager: [
    { to: '/sellers', labelKey: 'nav_sellers', icon: <IconUsers /> },
    { to: '/reports', labelKey: 'nav_reports', icon: <IconChartBar /> },
  ],
}

const PAGE_TITLES: { test: (path: string) => boolean; titleKey: StringKey }[] = [
  { test: (p) => p === '/dashboard', titleKey: 'page_title_dashboard' },
  { test: (p) => p.startsWith('/tenants/'), titleKey: 'page_title_tenant_detail' },
  { test: (p) => p === '/platform-broadcasts', titleKey: 'page_title_platform_broadcasts' },
  { test: (p) => p === '/tenant', titleKey: 'page_title_tenant' },
  { test: (p) => p === '/sellers', titleKey: 'page_title_sellers' },
  { test: (p) => p === '/broadcasts', titleKey: 'page_title_broadcasts' },
  { test: (p) => p === '/reports', titleKey: 'page_title_reports' },
]

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase()
}

function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage()
  return (
    <div className="language-switcher" role="group" aria-label="Til">
      {LANGUAGES.map((code) => (
        <button
          key={code}
          type="button"
          className={`language-switcher-option${code === language ? ' active' : ''}`}
          onClick={() => setLanguage(code as Language)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { language, t } = useLanguage()
  const location = useLocation()
  const links = (user?.role && NAV_BY_ROLE[user.role]) || []
  const [logoutOpen, setLogoutOpen] = useState(false)
  const pageTitleKey = PAGE_TITLES.find((entry) => entry.test(location.pathname))?.titleKey
  const pageTitle = pageTitleKey ? t(pageTitleKey) : t('page_title_fallback')

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <Brand />
        </div>

        <nav className="sidebar-nav">
          <div className="nav-group-label">{t('nav_group_label')}</div>
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              {link.icon}
              {t(link.labelKey)}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="field" style={{ marginBottom: '0.4rem' }}>
            <label>{t('language_label')}</label>
            <LanguageSwitcher />
          </div>
          <div className="user-card">
            <span className="user-avatar">{user?.username ? initials(user.username) : '—'}</span>
            <div className="user-meta">
              <div className="name">{user?.username}</div>
              <div className="role">{user?.role ? roleLabel(language, user.role) : '—'}</div>
            </div>
          </div>
          <button
            type="button"
            className="ghost sm danger sidebar-logout"
            onClick={() => setLogoutOpen(true)}
          >
            <IconLogout />
            <span className="sidebar-logout-label">{t('logout')}</span>
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <h1>{pageTitle}</h1>
        </header>
        <main className="app-content">
          <Outlet />
        </main>
      </div>

      <ConfirmDialog
        open={logoutOpen}
        title={t('logout_confirm_title')}
        description={t('logout_confirm_description')}
        confirmLabel={t('logout')}
        cancelLabel={t('cancel')}
        tone="danger"
        onConfirm={logout}
        onCancel={() => setLogoutOpen(false)}
      />
    </div>
  )
}
