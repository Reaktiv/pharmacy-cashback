import { useRef, useState, type DragEvent } from 'react'
import { apiFetch, ApiError } from '../api/client'
import type { BroadcastMedia } from '../api/types'
import { useLanguage, type TFunction } from '../lib/i18n'
import {
  IconUploadCloud,
  IconImagePicture,
  IconVideoCamera,
  IconX,
  IconAlertCircle,
} from './Icons'

const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const MAX_VIDEO_BYTES = 50 * 1024 * 1024

export interface AttachedMedia {
  id: number
  mediaType: 'image' | 'video'
  previewUrl: string
  fileName: string
  sizeBytes: number
}

function validate(file: File, t: TFunction): string | null {
  const isImage = file.type.startsWith('image/')
  const isVideo = file.type.startsWith('video/')
  if (!isImage && !isVideo) return t('media_only_image_or_video')
  if (isImage && file.size > MAX_IMAGE_BYTES) return t('media_image_too_large')
  if (isVideo && file.size > MAX_VIDEO_BYTES) return t('media_video_too_large')
  return null
}

/** Attach one image or video to a broadcast. Uploads immediately on
 * selection (rather than waiting for the whole composer form to submit) so
 * the tenant admin sees upload/validation errors right away — the local
 * object-URL preview (from the raw File, no round trip) shows instantly,
 * then swaps in the server-assigned media id once the upload resolves. */
export default function MediaAttach({
  value,
  onChange,
}: {
  value: AttachedMedia | null
  onChange: (media: AttachedMedia | null) => void
}) {
  const { t } = useLanguage()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFile = async (file: File) => {
    setError(null)
    const validationError = validate(file, t)
    if (validationError) {
      setError(validationError)
      return
    }

    const previewUrl = URL.createObjectURL(file)
    const mediaType: 'image' | 'video' = file.type.startsWith('image/') ? 'image' : 'video'
    onChange({ id: -1, mediaType, previewUrl, fileName: file.name, sizeBytes: file.size })

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const uploaded = await apiFetch<BroadcastMedia>('/api/broadcast-media/', {
        method: 'POST',
        body: formData,
      })
      onChange({
        id: uploaded.id,
        mediaType: uploaded.media_type,
        previewUrl,
        fileName: uploaded.original_filename,
        sizeBytes: uploaded.size_bytes,
      })
    } catch (err) {
      setError(err instanceof ApiError ? JSON.stringify(err.data) : t('media_upload_failed'))
      onChange(null)
      URL.revokeObjectURL(previewUrl)
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragActive(false)
    const file = event.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  const handleRemove = () => {
    if (value) URL.revokeObjectURL(value.previewUrl)
    onChange(null)
    setError(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  if (value) {
    return (
      <div className="media-attachment">
        {value.mediaType === 'image' ? (
          <img src={value.previewUrl} alt="" className="media-attachment-thumb" />
        ) : (
          <video src={value.previewUrl} className="media-attachment-thumb" muted />
        )}
        <div className="media-attachment-info">
          <div className="name">{value.fileName}</div>
          <div className="meta">
            {uploading ? (
              <span className="media-upload-progress">{t('media_uploading')}</span>
            ) : (
              t('media_size_mb', { size: (value.sizeBytes / (1024 * 1024)).toFixed(1) })
            )}
          </div>
        </div>
        <button type="button" className="ghost sm" onClick={handleRemove} disabled={uploading}>
          <IconX />
        </button>
      </div>
    )
  }

  return (
    <div>
      <div
        className={`media-dropzone${dragActive ? ' drag-active' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <IconUploadCloud />
        <span>{t('media_dropzone_instructions')}</span>
        <span className="dz-hint">
          <span className="dz-hint-icon">
            <IconImagePicture /> {t('media_hint_image')}
          </span>
          <span className="dz-hint-icon">
            <IconVideoCamera /> {t('media_hint_video')}
          </span>
        </span>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*,video/*"
        style={{ display: 'none' }}
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) handleFile(file)
        }}
      />
      {error && (
        <div className="error-banner" style={{ marginTop: '0.75rem', marginBottom: 0 }}>
          <IconAlertCircle />
          <span>{error}</span>
        </div>
      )}
    </div>
  )
}
