import type { Role } from '../api/types'
import type { Language, StringKey } from './i18n'
import { translate } from './i18n'

const ROLE_KEYS: Record<Role, StringKey> = {
  superadmin: 'role_superadmin',
  tenant_admin: 'role_tenant_admin',
  branch_manager: 'role_branch_manager',
  seller: 'role_seller',
  unassigned: 'role_unassigned',
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

// The `Record<Role, StringKey>` maps above are exhaustive for the *typed*
// Role union, but a value straight off the API (an unrecognized role
// string the frontend hasn't been taught about yet) can still slip past
// TypeScript at runtime — fall back to the raw value instead of crashing
// on an undefined lookup (translate() would otherwise index undefined).
export function roleLabel(language: Language, role: Role): string {
  const key = ROLE_KEYS[role]
  return key ? translate(language, key) : String(role)
}

export function activeStatusLabel(language: Language, status: 'active' | 'inactive'): string {
  const key = ACTIVE_STATUS_KEYS[status]
  return key ? translate(language, key) : String(status)
}

export function broadcastStatusLabel(
  language: Language,
  status: 'draft' | 'sending' | 'sent' | 'failed'
): string {
  const key = BROADCAST_STATUS_KEYS[status]
  return key ? translate(language, key) : String(status)
}
