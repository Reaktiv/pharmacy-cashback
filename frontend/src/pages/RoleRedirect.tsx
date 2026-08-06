import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import EmptyState from '../components/EmptyState'
import { IconCrossShield } from '../components/Icons'
import { useLanguage } from '../lib/i18n'

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
  const { t } = useLanguage()
  if (!user?.role || !(user.role in LANDING_BY_ROLE)) {
    return (
      <div className="panel">
        <EmptyState
          icon={<IconCrossShield />}
          title={t('role_redirect_no_panel_title')}
          subtitle={
            user?.role === 'seller'
              ? t('role_redirect_seller_subtitle')
              : t('role_redirect_no_role_subtitle')
          }
        />
      </div>
    )
  }
  return <Navigate to={LANDING_BY_ROLE[user.role]} replace />
}
