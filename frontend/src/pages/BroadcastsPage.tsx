import { useEffect, useState } from 'react'
import { apiFetch, apiFetchObjectUrl, ApiError } from '../api/client'
import type { Broadcast, BroadcastMedia } from '../api/types'
import { broadcastStatusLabel } from '../lib/labels'
import { useLanguage } from '../lib/i18n'
import { plainTextLength, renderBroadcastMessageHtml, sanitizeRichTextHtml } from '../lib/richText'
import EmptyState from '../components/EmptyState'
import { SkeletonTable } from '../components/Skeleton'
import RichTextEditor from '../components/RichTextEditor'
import MediaAttach, { type AttachedMedia } from '../components/MediaAttach'
import TelegramPreview from '../components/TelegramPreview'
import {
  IconAlertCircle,
  IconMegaphone,
  IconSend,
  IconImagePicture,
  IconVideoCamera,
} from '../components/Icons'

const TEXT_ONLY_LIMIT = 4096
const MEDIA_CAPTION_LIMIT = 1024

function asArray<T>(data: T[] | { results: T[] }): T[] {
  return Array.isArray(data) ? data : data.results
}

function BroadcastMediaThumb({ media }: { media: BroadcastMedia }) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    apiFetchObjectUrl(media.url).then((u) => {
      if (cancelled) {
        URL.revokeObjectURL(u)
        return
      }
      objectUrl = u
      setUrl(u)
    })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [media.url])

  if (!url) return <span className="skeleton" style={{ width: 40, height: 40, borderRadius: 8, display: 'inline-block' }} />

  return media.media_type === 'image' ? (
    <img src={url} alt="" style={{ width: 40, height: 40, borderRadius: 8, objectFit: 'cover' }} />
  ) : (
    // eslint-disable-next-line jsx-a11y/media-has-caption
    <video src={url} style={{ width: 40, height: 40, borderRadius: 8, objectFit: 'cover' }} muted />
  )
}

export default function BroadcastsPage() {
  const { t, language } = useLanguage()
  const [broadcasts, setBroadcasts] = useState<Broadcast[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sendingId, setSendingId] = useState<number | null>(null)

  const [composerKey, setComposerKey] = useState(0)
  const [title, setTitle] = useState('')
  const [bodyHtml, setBodyHtml] = useState('')
  const [media, setMedia] = useState<AttachedMedia | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState<'draft' | 'send' | null>(null)

  const load = () => {
    apiFetch<Broadcast[] | { results: Broadcast[] }>('/api/broadcasts/').then((data) =>
      setBroadcasts(asArray(data))
    )
  }

  useEffect(load, [])

  const sanitizedBody = sanitizeRichTextHtml(bodyHtml)
  const limit = media ? MEDIA_CAPTION_LIMIT : TEXT_ONLY_LIMIT
  const length = plainTextLength(renderBroadcastMessageHtml(title, sanitizedBody))
  const overLimit = length > limit
  const mediaStillUploading = media !== null && media.id === -1

  const resetComposer = () => {
    setTitle('')
    setBodyHtml('')
    if (media) URL.revokeObjectURL(media.previewUrl)
    setMedia(null)
    setComposerKey((k) => k + 1)
  }

  const handleSubmit = async (action: 'draft' | 'send') => {
    setFormError(null)
    if (mediaStillUploading) {
      setFormError(t('broadcast_media_still_uploading'))
      return
    }
    if (overLimit) {
      setFormError(t('broadcast_over_char_limit', { limit, length }))
      return
    }
    if (!title.trim()) {
      setFormError(t('broadcast_title_required'))
      return
    }

    setSubmitting(action)
    try {
      const created = await apiFetch<Broadcast>('/api/broadcasts/', {
        method: 'POST',
        body: JSON.stringify({
          title,
          body: bodyHtml,
          ...(media ? { media_id: media.id } : {}),
        }),
      })
      if (action === 'send') {
        await apiFetch(`/api/broadcasts/${created.id}/send/`, { method: 'POST' })
      }
      resetComposer()
      load()
    } catch (err) {
      setFormError(err instanceof ApiError ? JSON.stringify(err.data) : t('broadcast_create_error'))
    } finally {
      setSubmitting(null)
    }
  }

  const handleSend = async (id: number) => {
    setSendingId(id)
    setError(null)
    try {
      await apiFetch(`/api/broadcasts/${id}/send/`, { method: 'POST' })
      load()
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('broadcast_send_error'))
    } finally {
      setSendingId(null)
    }
  }

  if (!broadcasts) return <SkeletonTable rows={6} />

  return (
    <div>
      {error && (
        <div className="error-banner">
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}

      <div className="section-head" style={{ marginTop: 0 }}>
        <h2>{t('broadcasts_heading')}</h2>
      </div>
      <div className="table-card">
        {broadcasts.length === 0 ? (
          <EmptyState
            icon={<IconMegaphone />}
            title={t('broadcasts_empty_title')}
            subtitle={t('broadcasts_empty_subtitle')}
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t('th_title')}</th>
                  <th>{t('th_media')}</th>
                  <th>{t('status_label')}</th>
                  <th>{t('th_sent')}</th>
                  <th>{t('th_failed')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {broadcasts.map((b) => (
                  <tr key={b.id}>
                    <td>{b.title}</td>
                    <td>
                      {b.media ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <BroadcastMediaThumb media={b.media} />
                          <span className="pill">
                            {b.media.media_type === 'image' ? <IconImagePicture /> : <IconVideoCamera />}
                            {b.media.media_type === 'image' ? t('media_type_image') : t('media_type_video')}
                          </span>
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`pill ${b.status}`}>{broadcastStatusLabel(language, b.status)}</span>
                    </td>
                    <td className="num">{b.sent_count}</td>
                    <td className="num">{b.failed_count}</td>
                    <td>
                      {b.status === 'draft' && (
                        <button
                          type="button"
                          className="secondary sm"
                          disabled={sendingId === b.id}
                          onClick={() => handleSend(b.id)}
                        >
                          {sendingId === b.id ? t('broadcast_sending') : t('broadcast_send_button')}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section-head">
        <div>
          <h2>{t('broadcast_new_heading')}</h2>
          <p>{t('broadcast_new_description')}</p>
        </div>
      </div>
      <div className="panel">
        {formError && (
          <div className="error-banner">
            <IconAlertCircle />
            <span>{formError}</span>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.3fr) minmax(0, 1fr)', gap: '1.5rem' }}>
          <div>
            <div className="field wide">
              <label htmlFor="broadcast-title">{t('th_title')}</label>
              <input
                id="broadcast-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t('broadcast_title_placeholder')}
              />
            </div>
            <div className="field wide">
              <label>{t('field_text')}</label>
              <RichTextEditor
                key={composerKey}
                initialValue=""
                onChange={setBodyHtml}
                placeholder={t('broadcast_text_placeholder')}
              />
              <div className={`char-counter${overLimit ? ' over-limit' : ''}`}>
                {overLimit && <IconAlertCircle />}
                {t('broadcast_char_counter', { length, limit })}
                {media ? t('broadcast_media_attached_suffix') : ''}
              </div>
            </div>
            <div className="field wide">
              <label>{t('field_media_optional')}</label>
              <MediaAttach key={`media-${composerKey}`} value={media} onChange={setMedia} />
            </div>

            <div style={{ display: 'flex', gap: '0.6rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                className="secondary"
                disabled={submitting !== null || mediaStillUploading || overLimit}
                onClick={() => handleSubmit('draft')}
              >
                {submitting === 'draft' ? t('saving') : t('broadcast_save_draft_button')}
              </button>
              <button
                type="button"
                disabled={submitting !== null || mediaStillUploading || overLimit}
                onClick={() => handleSubmit('send')}
              >
                <IconSend />
                {submitting === 'send' ? t('broadcast_sending') : t('broadcast_send_now_button')}
              </button>
            </div>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.8rem', fontWeight: 700, color: 'var(--gray-600)' }}>
              {t('broadcast_preview_label')}
            </label>
            <TelegramPreview title={title} bodyHtml={bodyHtml} media={media} />
          </div>
        </div>
      </div>
    </div>
  )
}
