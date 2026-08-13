// 'unassigned' is UserProfile.Role.UNASSIGNED's real value (apps/accounts/
// models.py) — the default for any freshly created login (e.g. `manage.py
// createsuperuser`, which sets Django's own is_superuser flag but never
// touches this app-level role) until an admin explicitly assigns one. A
// user can legitimately reach the panel in this state, so it has to be a
// real case here rather than something every Role-keyed lookup can assume
// away — see RoleRedirect.tsx's "no panel for this role" screen and
// lib/labels.ts's ROLE_KEYS.
export type Role = 'superadmin' | 'tenant_admin' | 'branch_manager' | 'seller' | 'unassigned'

export interface Tenant {
  id: number
  name: string
  slug: string
  is_active: boolean
  cashback_rate: string
  min_redeem_amount: string
  points_expiry_days: number | null
  default_daily_txn_limit: number | null
  broadcast_quota: number | null
  broadcasts_sent_this_month: number
  branch_limit: number | null
  branches_count: number
  has_logo: boolean
  created_at: string
}

export interface TenantBot {
  id: number
  tenant: number
  username: string
  webhook_secret: string
  is_active: boolean
}

export interface GlobalSettings {
  max_cashback_rate: string
  max_redeem_percent: string
  max_check_amount: string
  max_daily_redemptions_per_customer: number
}

export interface Branch {
  id: number
  name: string
  address: string
  is_active: boolean
}

export interface Seller {
  id: number
  branch: number
  phone: string
  full_name: string
  is_active: boolean
  daily_txn_limit: number | null
}

export interface BranchManager {
  id: number
  username: string
  branch: number
  branch_name: string
  is_active: boolean
}

export interface TenantAdmin {
  id: number
  username: string
  tenant: number
  tenant_name: string
  is_active: boolean
}

export interface BroadcastMedia {
  id: number
  media_type: 'image' | 'video'
  original_filename: string
  size_bytes: number
  url: string
  created_at: string
}

export interface Broadcast {
  id: number
  title: string
  body: string
  media: BroadcastMedia | null
  status: 'draft' | 'sending' | 'sent' | 'failed'
  sent_count: number
  failed_count: number
  created_at: string
  sent_at: string | null
}

export interface PlatformBroadcastMedia {
  id: number
  media_type: 'image' | 'video'
  original_filename: string
  size_bytes: number
  url: string
  created_at: string
}

export interface PlatformBroadcast {
  id: number
  title: string
  body: string
  media: PlatformBroadcastMedia | null
  status: 'draft' | 'sending' | 'sent' | 'failed'
  sent_count: number
  failed_count: number
  tenant_count: number
  created_at: string
  sent_at: string | null
}

export interface CrossTenantDashboardRow {
  tenant_id: number
  tenant_name: string
  bot_username: string | null
  bot_active: boolean | null
  customers: number
  active_30d: number
  today_txns: number
  total_liability: number
  status: 'active' | 'inactive'
}

export interface BranchReportRow {
  branch_id: number | null
  branch_name: string
  total_earned: number
  total_spent: number
  outstanding: number
}

export interface SellerReportRow {
  seller_id: number | null
  seller_name: string
  txn_count: number
  avg_check: number
  flagged_count: number
}

export interface DailyReportRow {
  day: string
  total_earned: number
  total_spent: number
}

export interface SellerTransactionRow {
  id: number
  created_at: string
  customer_phone: string
  check_amount: number
  cash_paid: number
  cashback_earned: number
  cashback_spent: number
  no_cashback: boolean
  type: 'earn' | 'spend' | 'reversal'
  status: 'active' | 'reversed'
  flagged: boolean
}

export interface SellerTransactionsPage {
  results: SellerTransactionRow[]
  count: number
  totals: {
    check_amount: number
    cashback_earned: number
    cashback_spent: number
  }
}

export interface MeProfile {
  username: string
  role: Role
  role_display: string
  tenant_name: string | null
  branch_name: string | null
  full_name: string
  phone: string
  has_avatar: boolean
  tenant_has_logo: boolean
  // Only meaningful (non-null) for role === 'superadmin' — the product-wide
  // brand every other role sees replaced by their own tenant's name/logo.
  platform_name: string | null
  platform_has_logo: boolean | null
}

export interface PlatformBranding {
  name: string
  has_logo: boolean
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
