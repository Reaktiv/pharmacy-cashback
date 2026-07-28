export type Role = 'superadmin' | 'tenant_admin' | 'branch_manager' | 'seller'

export interface Tenant {
  id: number
  name: string
  slug: string
  is_active: boolean
  cashback_rate: string
  min_redeem_amount: string
  points_expiry_days: number | null
  default_daily_txn_limit: number | null
  created_at: string
}

export interface Bot {
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

export interface Broadcast {
  id: number
  title: string
  body: string
  status: 'draft' | 'sending' | 'sent'
  sent_count: number
  failed_count: number
  created_at: string
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

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
