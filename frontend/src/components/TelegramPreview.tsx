import { renderBroadcastMessageHtml, sanitizeRichTextHtml } from '../lib/richText'
import { useLanguage } from '../lib/i18n'
import type { AttachedMedia } from './MediaAttach'

/** Approximates how the message will actually render inside Telegram:
 * media (if any) at the top, caption/text below, bubble-shaped. Body HTML
 * is run through the same client-side allowlist sanitizer used for the
 * character counter before being rendered here — never the raw editor
 * output — so this is exactly the safe subset the server will also send. */
export default function TelegramPreview({
  title,
  bodyHtml,
  media,
}: {
  title: string
  bodyHtml: string
  media: AttachedMedia | null
}) {
  const { t } = useLanguage()
  const sanitizedBody = sanitizeRichTextHtml(bodyHtml)
  const rendered = renderBroadcastMessageHtml(title, sanitizedBody)
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const isEmpty = !title.trim() && !sanitizedBody.trim() && !media

  return (
    <div className="tg-preview-shell">
      <div className="tg-bubble">
        {isEmpty ? (
          <div className="tg-bubble-empty">{t('telegram_preview_placeholder')}</div>
        ) : (
          <>
            {media && (
              <div className="tg-bubble-media">
                {media.mediaType === 'image' ? (
                  <img src={media.previewUrl} alt="" />
                ) : (
                  // eslint-disable-next-line jsx-a11y/media-has-caption
                  <video src={media.previewUrl} controls muted />
                )}
              </div>
            )}
            {rendered && <div className="tg-bubble-text" dangerouslySetInnerHTML={{ __html: rendered }} />}
            <div className="tg-bubble-time">{time}</div>
          </>
        )}
      </div>
    </div>
  )
}
