import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiFetch, apiFetchObjectUrl, ApiError } from '../api/client'
import type { MeProfile } from '../api/types'
import { roleLabel } from '../lib/labels'
import { LANGUAGES, useLanguage, type Language } from '../lib/i18n'
import DetailDrawer from './DetailDrawer'
import SettingsGroup, { SettingsGroupBody } from './SettingsGroup'
import { IconAlertCircle, IconCheckCircle, IconImagePicture, IconX } from './Icons'

const AVATAR_MAX_BYTES = 5 * 1024 * 1024

interface ProfileDrawerProps {
  open: boolean
  onClose: () => void
  profile: MeProfile | null
  avatarUrl: string | null
  onSaved: (
    profile: MeProfile,
    avatarFile: File | null,
    removedAvatar: boolean,
    platformLogoFile?: File | null,
    removedPlatformLogo?: boolean,
  ) => void
}

/** Self-service account center for every role — identity header, then
 * grouped sections (personal info, language, platform branding for
 * superadmin, security) instead of one long vertical form. */
export default function ProfileDrawer({ open, onClose, profile, avatarUrl, onSaved }: ProfileDrawerProps) {
  const { t, language, setLanguage } = useLanguage()
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const platformLogoInputRef = useRef<HTMLInputElement>(null)

  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [avatarFile, setAvatarFile] = useState<File | null>(null)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)
  const [removeAvatar, setRemoveAvatar] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [platformName, setPlatformName] = useState('')
  const [platformLogoUrl, setPlatformLogoUrl] = useState<string | null>(null)
  const [platformLogoFile, setPlatformLogoFile] = useState<File | null>(null)
  const [platformLogoPreview, setPlatformLogoPreview] = useState<string | null>(null)
  const [removePlatformLogo, setRemovePlatformLogo] = useState(false)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordSaved, setPasswordSaved] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)

  const isSuperadmin = profile?.role === 'superadmin'

  // Persisted on UserProfile.language (not just the local i18n context) so
  // it's the same value apps.seller_web.i18n.get_language reads for a
  // seller's till pages — otherwise switching it here would only ever
  // affect this browser's React session, never the seller-web account it
  // was meant to change (see apps/seller_web/i18n.py's docstring).
  const handleLanguageChange = async (code: Language) => {
    setLanguage(code)
    if (!profile) return
    try {
      const updated = await apiFetch<MeProfile>('/api/me/', {
        method: 'PATCH',
        body: JSON.stringify({ language: code }),
      })
      onSaved(updated, null, false)
    } catch {
      // Best-effort: the UI already reflects the new language locally even
      // if persisting it server-side fails.
    }
  }

  useEffect(() => {
    if (!open || !profile) return
    setFullName(profile.full_name)
    setPhone(profile.phone)
    setAvatarFile(null)
    setAvatarPreview(null)
    setRemoveAvatar(false)
    setError(null)
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setPasswordSaved(false)
    setPasswordError(null)

    setPlatformName(profile.platform_name ?? '')
    setPlatformLogoFile(null)
    setPlatformLogoPreview(null)
    setRemovePlatformLogo(false)
    if (profile.role === 'superadmin' && profile.platform_has_logo) {
      apiFetchObjectUrl('/api/branding/logo/').then(setPlatformLogoUrl).catch(() => setPlatformLogoUrl(null))
    } else {
      setPlatformLogoUrl(null)
    }
  }, [open, profile])

  useEffect(() => {
    return () => {
      if (avatarPreview) URL.revokeObjectURL(avatarPreview)
    }
  }, [avatarPreview])

  useEffect(() => {
    return () => {
      if (platformLogoPreview) URL.revokeObjectURL(platformLogoPreview)
    }
  }, [platformLogoPreview])

  const handleFile = (file: File) => {
    setError(null)
    if (!file.type.startsWith('image/')) {
      setError(t('profile_avatar_invalid_type'))
      return
    }
    if (file.size > AVATAR_MAX_BYTES) {
      setError(t('profile_avatar_too_large', { size: AVATAR_MAX_BYTES / (1024 * 1024) }))
      return
    }
    if (avatarPreview) URL.revokeObjectURL(avatarPreview)
    setAvatarFile(file)
    setAvatarPreview(URL.createObjectURL(file))
    setRemoveAvatar(false)
  }

  const handleRemoveAvatar = () => {
    if (avatarPreview) URL.revokeObjectURL(avatarPreview)
    setAvatarFile(null)
    setAvatarPreview(null)
    setRemoveAvatar(true)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handlePlatformLogoFile = (file: File) => {
    setError(null)
    if (!file.type.startsWith('image/')) {
      setError(t('profile_avatar_invalid_type'))
      return
    }
    if (file.size > AVATAR_MAX_BYTES) {
      setError(t('profile_avatar_too_large', { size: AVATAR_MAX_BYTES / (1024 * 1024) }))
      return
    }
    if (platformLogoPreview) URL.revokeObjectURL(platformLogoPreview)
    setPlatformLogoFile(file)
    setPlatformLogoPreview(URL.createObjectURL(file))
    setRemovePlatformLogo(false)
  }

  const handleRemovePlatformLogo = () => {
    if (platformLogoPreview) URL.revokeObjectURL(platformLogoPreview)
    setPlatformLogoFile(null)
    setPlatformLogoPreview(null)
    setRemovePlatformLogo(true)
    if (platformLogoInputRef.current) platformLogoInputRef.current.value = ''
  }

  const handleSave = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('full_name', fullName)
      formData.append('phone', phone)
      if (avatarFile) formData.append('avatar', avatarFile)
      if (removeAvatar) formData.append('remove_avatar', 'true')
      if (isSuperadmin) {
        formData.append('platform_name', platformName)
        if (platformLogoFile) formData.append('platform_logo', platformLogoFile)
        if (removePlatformLogo) formData.append('remove_platform_logo', 'true')
      }
      const updated = await apiFetch<MeProfile>('/api/me/', { method: 'PATCH', body: formData })
      onSaved(updated, avatarFile, removeAvatar, platformLogoFile, removePlatformLogo)
      onClose()
      navigate('/')
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('profile_save_error'))
    } finally {
      setSaving(false)
    }
  }

  const handleChangePassword = async (event: FormEvent) => {
    event.preventDefault()
    setPasswordError(null)
    setPasswordSaved(false)
    if (newPassword !== confirmPassword) {
      setPasswordError(t('password_mismatch_error'))
      return
    }
    setChangingPassword(true)
    try {
      await apiFetch('/api/me/change-password/', {
        method: 'POST',
        body: JSON.stringify({ old_password: currentPassword, new_password: newPassword }),
      })
      setPasswordSaved(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setPasswordError(err instanceof ApiError ? JSON.stringify(err.data) : t('password_change_error'))
    } finally {
      setChangingPassword(false)
    }
  }

  const shownAvatar = avatarPreview ?? (!removeAvatar ? avatarUrl : null)
  const initials = (fullName || profile?.username || '').slice(0, 2).toUpperCase()
  const shownPlatformLogo = platformLogoPreview ?? (!removePlatformLogo ? platformLogoUrl : null)

  return (
    <DetailDrawer open={open} title={t('profile_heading')} onClose={onClose}>
      {profile && (
        <>
          <div className="account-identity">
            <div className={`profile-avatar-preview${shownAvatar ? ' has-image' : ''}`}>
              {shownAvatar ? <img src={shownAvatar} alt="" /> : <span>{initials}</span>}
            </div>
            <div>
              <div className="account-identity-name">{fullName || profile.username}</div>
              <div className="account-identity-meta">
                <span className="status-badge active">{roleLabel(language, profile.role)}</span>
                {profile.tenant_name && <span className="pill">{profile.tenant_name}</span>}
                {profile.branch_name && <span className="pill">{profile.branch_name}</span>}
              </div>
            </div>
          </div>

          {error && (
            <div className="error-banner">
              <IconAlertCircle />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSave}>
            <SettingsGroup title={t('field_full_name')} description={t('th_login') + ': ' + profile.username}>
              <SettingsGroupBody>
                <div className="profile-avatar-picker" style={{ marginBottom: '1.1rem' }}>
                  <div className="profile-avatar-actions">
                    <button type="button" className="ghost sm" onClick={() => inputRef.current?.click()}>
                      <IconImagePicture />
                      {t('profile_change_photo')}
                    </button>
                    {shownAvatar && (
                      <button type="button" className="ghost sm danger" onClick={handleRemoveAvatar}>
                        <IconX />
                        {t('profile_remove_photo')}
                      </button>
                    )}
                  </div>
                  <input
                    ref={inputRef}
                    type="file"
                    accept="image/*"
                    style={{ display: 'none' }}
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      if (file) handleFile(file)
                    }}
                  />
                </div>

                <div className="field">
                  <label htmlFor="profile-full-name">{t('field_full_name')}</label>
                  <input id="profile-full-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="profile-phone">{t('field_phone')}</label>
                  <input
                    id="profile-phone"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder={t('phone_placeholder')}
                  />
                </div>
              </SettingsGroupBody>
            </SettingsGroup>

            <SettingsGroup title={t('language_label')}>
              <SettingsGroupBody>
                <div className="language-switcher" role="group" aria-label={t('language_label')}>
                  {LANGUAGES.map((code) => (
                    <button
                      key={code}
                      type="button"
                      className={`language-switcher-option${code === language ? ' active' : ''}`}
                      onClick={() => handleLanguageChange(code as Language)}
                    >
                      {code.toUpperCase()}
                    </button>
                  ))}
                </div>
              </SettingsGroupBody>
            </SettingsGroup>

            {isSuperadmin && (
              <SettingsGroup title={t('platform_branding_heading')}>
                <SettingsGroupBody>
                  <div className="profile-avatar-picker">
                    <div className={`profile-avatar-preview${shownPlatformLogo ? ' has-image' : ''}`}>
                      {shownPlatformLogo ? (
                        <img src={shownPlatformLogo} alt="" />
                      ) : (
                        <span>{(platformName || 'PC').slice(0, 2).toUpperCase()}</span>
                      )}
                    </div>
                    <div className="profile-avatar-actions">
                      <button type="button" className="ghost sm" onClick={() => platformLogoInputRef.current?.click()}>
                        <IconImagePicture />
                        {t('tenant_admin_change_logo')}
                      </button>
                      {shownPlatformLogo && (
                        <button type="button" className="ghost sm danger" onClick={handleRemovePlatformLogo}>
                          <IconX />
                          {t('tenant_admin_remove_logo')}
                        </button>
                      )}
                    </div>
                    <input
                      ref={platformLogoInputRef}
                      type="file"
                      accept="image/*"
                      style={{ display: 'none' }}
                      onChange={(event) => {
                        const file = event.target.files?.[0]
                        if (file) handlePlatformLogoFile(file)
                      }}
                    />
                  </div>
                  <div className="field" style={{ marginTop: '1.1rem' }}>
                    <label htmlFor="platform-name">{t('field_platform_name')}</label>
                    <input id="platform-name" value={platformName} onChange={(e) => setPlatformName(e.target.value)} />
                  </div>
                </SettingsGroupBody>
              </SettingsGroup>
            )}

            <button type="submit" disabled={saving} style={{ width: '100%' }}>
              {saving ? t('saving') : t('save')}
            </button>
          </form>

          <SettingsGroup title={t('password_section_heading')}>
            <SettingsGroupBody>
              <form onSubmit={handleChangePassword}>
                <div className="field">
                  <label htmlFor="profile-current-password">{t('field_current_password')}</label>
                  <input
                    id="profile-current-password"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                </div>
                <div className="field">
                  <label htmlFor="profile-new-password">{t('field_new_password')}</label>
                  <input
                    id="profile-new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                </div>
                <div className="field">
                  <label htmlFor="profile-confirm-password">{t('field_confirm_new_password')}</label>
                  <input
                    id="profile-confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                  />
                </div>

                {passwordError && (
                  <div className="error-banner" style={{ marginBottom: '0.9rem' }}>
                    <IconAlertCircle />
                    <span>{passwordError}</span>
                  </div>
                )}
                {passwordSaved && !passwordError && (
                  <div className="toast" style={{ marginBottom: '0.9rem' }}>
                    <IconCheckCircle />
                    {t('password_changed_toast')}
                  </div>
                )}

                <button type="submit" className="danger" disabled={changingPassword} style={{ width: '100%' }}>
                  {changingPassword ? t('saving') : t('change_password_button')}
                </button>
              </form>
            </SettingsGroupBody>
          </SettingsGroup>
        </>
      )}
    </DetailDrawer>
  )
}
