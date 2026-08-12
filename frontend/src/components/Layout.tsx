import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { apiFetch, apiFetchObjectUrl } from '../api/client'
import type { MeProfile } from '../api/types'
import { roleLabel } from '../lib/labels'
import { useLanguage, type StringKey } from '../lib/i18n'
import Brand from './Logo'
import ConfirmDialog from './ConfirmDialog'
import ProfileDrawer from './ProfileDrawer'
import {
  IconGrid,
  IconBuilding,
  IconUsers,
  IconMegaphone,
  IconChartBar,
  IconLogout,
  IconMenu,
  IconX,
  IconUser,
  IconSettings,
} from './Icons'
import type { ReactNode } from 'react'

const NAV_BY_ROLE: Record<string, { to: string; labelKey: StringKey; icon: ReactNode }[]> = {
  superadmin: [
    { to: '/dashboard', labelKey: 'nav_dashboard', icon: <IconGrid /> },
    { to: '/platform-broadcasts', labelKey: 'nav_platform_broadcasts', icon: <IconMegaphone /> },
  ],
  tenant_admin: [
    { to: '/tenant', labelKey: 'nav_tenant', icon: <IconBuilding /> },
    { to: '/tenant/settings', labelKey: 'nav_tenant_settings', icon: <IconSettings /> },
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
  { test: (p) => p === '/tenant/settings', titleKey: 'page_title_tenant_settings' },
  { test: (p) => p === '/sellers', titleKey: 'page_title_sellers' },
  { test: (p) => p === '/broadcasts', titleKey: 'page_title_broadcasts' },
  { test: (p) => p === '/reports', titleKey: 'page_title_reports' },
]

// Matches the `@media (max-width: 680px)` breakpoint in index.css that
// switches the sidebar from a pushed column into an off-canvas drawer.
const MOBILE_BREAKPOINT_QUERY = '(max-width: 680px)'

/** Passed to every nested route page via <Outlet context={...}/> — lets a
 * page like TenantAdminPage (which edits Tenant.name/logo) tell the
 * sidebar/topbar brand to refetch after a save, without a full reload. */
export interface LayoutOutletContext {
  refreshBranding: () => void
}

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase()
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { t, language } = useLanguage()
  const location = useLocation()
  const links = (user?.role && NAV_BY_ROLE[user.role]) || []
  const [logoutOpen, setLogoutOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [meProfile, setMeProfile] = useState<MeProfile | null>(null)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const avatarUrlRef = useRef<string | null>(null)
  const [brandLogoUrl, setBrandLogoUrl] = useState<string | null>(null)
  const brandLogoUrlRef = useRef<string | null>(null)
  // Open by default on desktop, closed by default on phone-sized screens —
  // same hamburger-toggled menu either way, just a different starting state.
  const [menuOpen, setMenuOpen] = useState(() => !window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches)
  const pageTitleKey = PAGE_TITLES.find((entry) => entry.test(location.pathname))?.titleKey
  const pageTitle = pageTitleKey ? t(pageTitleKey) : t('page_title_fallback')

  const setAvatar = (url: string | null) => {
    if (avatarUrlRef.current) URL.revokeObjectURL(avatarUrlRef.current)
    avatarUrlRef.current = url
    setAvatarUrl(url)
  }

  const setBrandLogo = (url: string | null) => {
    if (brandLogoUrlRef.current) URL.revokeObjectURL(brandLogoUrlRef.current)
    brandLogoUrlRef.current = url
    setBrandLogoUrl(url)
  }

  // Re-fetchable on demand (not just on mount) — a tenant_admin renaming
  // their pharmacy or uploading a logo happens on a nested route page
  // (TenantAdminPage), which reaches this via useOutletContext() below to
  // refresh the sidebar/topbar brand without a full reload.
  const loadMe = useCallback(() => {
    apiFetch<MeProfile>('/api/me/')
      .then((data) => {
        setMeProfile(data)
        if (data.has_avatar) {
          apiFetchObjectUrl('/api/me/avatar/').then(setAvatar).catch(() => setAvatar(null))
        } else {
          setAvatar(null)
        }
        if (data.role === 'superadmin' && data.platform_has_logo) {
          apiFetchObjectUrl('/api/branding/logo/').then(setBrandLogo).catch(() => setBrandLogo(null))
        } else if (data.role !== 'superadmin' && data.tenant_has_logo) {
          apiFetchObjectUrl('/api/me/tenant-logo/').then(setBrandLogo).catch(() => setBrandLogo(null))
        } else {
          setBrandLogo(null)
        }
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    loadMe()
    return () => {
      if (avatarUrlRef.current) URL.revokeObjectURL(avatarUrlRef.current)
      if (brandLogoUrlRef.current) URL.revokeObjectURL(brandLogoUrlRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // A nav click while the menu is showing as an off-canvas drawer (phone)
  // should close it behind the new page, same as any mobile drawer nav.
  const closeMenuOnMobile = () => {
    if (window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches) setMenuOpen(false)
  }

  const displayName = meProfile?.full_name || user?.username || ''
  // Every role except superadmin sees their own pharmacy's identity instead
  // of the product's own brand — superadmin is the only account the
  // "Pharmacy Cashback" name/logo itself still belongs to (see
  // MeSerializer.platform_name).
  const brandName =
    (meProfile?.role === 'superadmin' ? meProfile.platform_name : meProfile?.tenant_name) ||
    'Pharmacy Cashback'

  return (
    <div className="app-shell">
      {menuOpen && <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />}

      <aside className={`sidebar${menuOpen ? ' open' : ' closed'}`}>
        <div className="sidebar-brand">
          <Brand name={brandName} logoUrl={brandLogoUrl} />
        </div>

        <div className="sidebar-profile-card">
          <span className={`sidebar-profile-avatar${avatarUrl ? ' has-image' : ''}`}>
            {avatarUrl ? <img src={avatarUrl} alt="" /> : displayName ? initials(displayName) : '—'}
          </span>
          <div className="sidebar-profile-name">{displayName || '—'}</div>
          <div className="sidebar-profile-role">{meProfile ? roleLabel(language, meProfile.role) : '—'}</div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-group-label">{t('nav_group_label')}</div>
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end
              onClick={closeMenuOnMobile}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              {link.icon}
              {t(link.labelKey)}
            </NavLink>
          ))}
        </nav>

        <button type="button" className="ghost sm sidebar-profile-btn" onClick={() => setProfileOpen(true)}>
          <IconUser />
          {t('profile_link_label')}
        </button>
        <button
          type="button"
          className="ghost sm danger sidebar-logout"
          onClick={() => setLogoutOpen(true)}
        >
          <IconLogout />
          {t('logout')}
        </button>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div className="app-topbar-left">
            <button
              type="button"
              className="hamburger-btn"
              onClick={() => setMenuOpen((open) => !open)}
              aria-label={t('menu_toggle_hint')}
              title={t('menu_toggle_hint')}
            >
              {menuOpen ? <IconX /> : <IconMenu />}
            </button>
            <h1>{pageTitle}</h1>
          </div>
        </header>
        <main className="app-content">
          <Outlet context={{ refreshBranding: loadMe }} />
        </main>
      </div>

      <ProfileDrawer
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        profile={meProfile}
        avatarUrl={avatarUrl}
        onSaved={(updated, avatarFile, removedAvatar, platformLogoFile, removedPlatformLogo) => {
          setMeProfile(updated)
          if (avatarFile) setAvatar(URL.createObjectURL(avatarFile))
          else if (removedAvatar) setAvatar(null)
          // brandName re-derives from `updated` automatically on the next
          // render (see the brandName const above) — only the logo image
          // itself needs an explicit refresh here, same as avatar above.
          if (updated.role === 'superadmin') {
            if (platformLogoFile) setBrandLogo(URL.createObjectURL(platformLogoFile))
            else if (removedPlatformLogo) setBrandLogo(null)
          }
        }}
      />

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
