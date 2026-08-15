import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { apiFetch, apiFetchObjectUrl } from '../api/client'
import type { MeProfile } from '../api/types'
import { useLanguage, type StringKey } from '../lib/i18n'
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
  IconSettings,
  IconUser,
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
 * page like TenantSettingsPage (which edits Tenant.name/logo) tell the
 * layout to refetch the ['me'] query after a save, without a full reload. */
export interface LayoutOutletContext {
  refreshBranding: () => void
}

/** The one place /api/me/ is fetched — every page reads it from this same
 * cache entry (staleTime set globally in main.tsx) instead of each doing
 * its own fetch. */
const ME_QUERY_KEY = ['me'] as const

function initials(name: string): string {
  return name.slice(0, 2).toUpperCase()
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { t, language, setLanguage } = useLanguage()
  const location = useLocation()
  const queryClient = useQueryClient()
  const links = (user?.role && NAV_BY_ROLE[user.role]) || []
  const [logoutOpen, setLogoutOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const avatarUrlRef = useRef<string | null>(null)
  // Open by default on desktop, closed by default on phone-sized screens —
  // same hamburger-toggled menu either way, just a different starting state.
  const [menuOpen, setMenuOpen] = useState(() => !window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches)
  const pageTitleKey = PAGE_TITLES.find((entry) => entry.test(location.pathname))?.titleKey
  const pageTitle = pageTitleKey ? t(pageTitleKey) : t('page_title_fallback')

  // The TanStack Query pilot (see main.tsx for the QueryClient's global
  // defaults): fetches once, cached under ['me'] for staleTime, refetched
  // on demand via `refetch` — replaces the old useEffect+apiFetch here.
  // Failures are swallowed (matching the old `.catch(() => {})`): a failed
  // /api/me/ just leaves the sidebar showing its '—' fallbacks, nothing
  // else in the shell depends on it hard enough to warrant an error state.
  const meQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => apiFetch<MeProfile>('/api/me/'),
  })
  const meProfile = meQuery.data ?? null

  const setAvatar = (url: string | null) => {
    if (avatarUrlRef.current) URL.revokeObjectURL(avatarUrlRef.current)
    avatarUrlRef.current = url
    setAvatarUrl(url)
  }

  // Account-level language wins over whatever this browser's localStorage
  // had (e.g. a fresh browser, or a change made from the profile drawer on
  // another device) — see ProfileDrawer's handleLanguageChange, which is
  // the only writer of this field. Deliberately keyed off meProfile.language
  // only, not the local `language` it compares against — including it would
  // re-run this effect right after the setLanguage call below.
  useEffect(() => {
    if (meProfile?.language && meProfile.language !== language) {
      setLanguage(meProfile.language)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meProfile?.language])

  // Fetches the avatar blob whenever has_avatar flips — including right
  // after ProfileDrawer's optimistic cache write (see onSaved below). That
  // write already sets `avatarUrl` itself from the freshly-uploaded File,
  // so on a false→true transition this ends up re-fetching the same image
  // once more than strictly necessary; harmless, and simpler than teaching
  // this effect to tell "real fetch" and "optimistic write" apart.
  useEffect(() => {
    if (!meProfile) return
    if (meProfile.has_avatar) {
      apiFetchObjectUrl('/api/me/avatar/').then(setAvatar).catch(() => setAvatar(null))
    } else {
      setAvatar(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meProfile?.has_avatar])

  useEffect(() => {
    return () => {
      if (avatarUrlRef.current) URL.revokeObjectURL(avatarUrlRef.current)
    }
  }, [])

  // A nav click while the menu is showing as an off-canvas drawer (phone)
  // should close it behind the new page, same as any mobile drawer nav.
  const closeMenuOnMobile = () => {
    if (window.matchMedia(MOBILE_BREAKPOINT_QUERY).matches) setMenuOpen(false)
  }

  const displayName = meProfile?.full_name || user?.username || ''

  return (
    <div className="app-shell">
      {menuOpen && <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />}

      <aside className={`sidebar${menuOpen ? ' open' : ' closed'}`}>
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

        <div className="sidebar-footer">
          <button type="button" className="sidebar-profile-trigger" onClick={() => setProfileOpen(true)}>
            <span className={`sidebar-profile-avatar${avatarUrl ? ' has-image' : ''}`}>
              {avatarUrl ? <img src={avatarUrl} alt="" /> : displayName ? initials(displayName) : <IconUser />}
            </span>
            <span className="sidebar-profile-trigger-name">{t('profile_link_label')}</span>
          </button>
          <button type="button" className="sidebar-logout" onClick={() => setLogoutOpen(true)}>
            <IconLogout />
            {t('logout')}
          </button>
        </div>
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
            <span className="app-topbar-title">{pageTitle}</span>
          </div>
        </header>
        <main className="app-content">
          <Outlet context={{ refreshBranding: () => meQuery.refetch() }} />
        </main>
      </div>

      <ProfileDrawer
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        profile={meProfile}
        avatarUrl={avatarUrl}
        onSaved={(updated, avatarFile, removedAvatar) => {
          // Already have the fresh server response from the PATCH — write
          // it straight into the cache instead of paying for a refetch.
          queryClient.setQueryData(ME_QUERY_KEY, updated)
          if (avatarFile) setAvatar(URL.createObjectURL(avatarFile))
          else if (removedAvatar) setAvatar(null)
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
