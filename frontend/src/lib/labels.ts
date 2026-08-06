import type { Role } from '../api/types'
import type { Language, StringKey } from './i18n'
import { translate } from './i18n'

const ROLE_KEYS: Record<Role, StringKey> = {
  superadmin: 'role_superadmin',
  tenant_admin: 'role_tenant_admin',
  branch_manager: 'role_branch_manager',
  seller: 'role_seller',
}

const ACTIVE_STATUS_KEYS: Record<'active' | 'inactive', StringKey> = {
  active: 'status_active',
  inactive: 'status_inactive',
}

const BROADCAST_STATUS_KEYS: Record<'draft' | 'sending' | 'sent' | 'failed', StringKey> = {
  draft: 'broadcast_status_draft',
  sending: 'broadcast_status_sending',
  sent: 'broadcast_status_sent',
  failed: 'broadcast_status_failed',
}

export function roleLabel(language: Language, role: Role): string {
  return translate(language, ROLE_KEYS[role])
}

export function activeStatusLabel(language: Language, status: 'active' | 'inactive'): string {
  return translate(language, ACTIVE_STATUS_KEYS[status])
}

export function broadcastStatusLabel(
  language: Language,
  status: 'draft' | 'sending' | 'sent' | 'failed'
): string {
  return translate(language, BROADCAST_STATUS_KEYS[status])
}
