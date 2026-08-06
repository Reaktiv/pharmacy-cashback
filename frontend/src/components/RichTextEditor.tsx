import { useEffect, useRef, useState } from 'react'
import { IconBold, IconItalic, IconUnderline, IconStrikethrough, IconCode, IconLinkChain } from './Icons'
import { useLanguage } from '../lib/i18n'

/** Wraps the current selection in `tagName` via Range.surroundContents —
 * works for a selection fully inside one node; falls back to insertHTML
 * for anything crossing element boundaries (surroundContents throws
 * there). Used for inline code, which execCommand has no native command
 * for. */
function wrapSelectionInTag(tagName: string): boolean {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return false
  const range = selection.getRangeAt(0)
  try {
    const el = document.createElement(tagName)
    range.surroundContents(el)
    selection.removeAllRanges()
    const newRange = document.createRange()
    newRange.selectNodeContents(el)
    selection.addRange(newRange)
    return true
  } catch {
    return false
  }
}

/** Uncontrolled by design — contentEditable's own DOM is the source of
 * truth while the user is typing, and `onChange` just informs the parent.
 * `initialValue` is applied once on mount only; to reset/clear the editor,
 * remount it by changing the `key` prop from the parent, rather than
 * fighting React's reconciliation over live cursor position. */
export default function RichTextEditor({
  initialValue = '',
  onChange,
  placeholder,
}: {
  initialValue?: string
  onChange: (html: string) => void
  placeholder?: string
}) {
  const { t } = useLanguage()
  const editorRef = useRef<HTMLDivElement>(null)
  const savedRangeRef = useRef<Range | null>(null)
  const [linkPopoverOpen, setLinkPopoverOpen] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')

  useEffect(() => {
    if (editorRef.current) editorRef.current.innerHTML = initialValue
    // Only ever applied once, on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const emitChange = () => {
    onChange(editorRef.current?.innerHTML ?? '')
  }

  const focusEditor = () => editorRef.current?.focus()

  const exec = (command: string) => {
    focusEditor()
    document.execCommand(command)
    emitChange()
  }

  const applyCode = () => {
    focusEditor()
    if (!wrapSelectionInTag('code')) {
      document.execCommand('insertHTML', false, `<code>${t('rte_code_placeholder')}</code>`)
    }
    emitChange()
  }

  const openLinkPopover = () => {
    const selection = window.getSelection()
    if (selection && selection.rangeCount > 0 && !selection.isCollapsed) {
      savedRangeRef.current = selection.getRangeAt(0).cloneRange()
    } else {
      savedRangeRef.current = null
    }
    setLinkUrl('')
    setLinkPopoverOpen(true)
  }

  const applyLink = () => {
    const url = linkUrl.trim()
    if (!url) return
    focusEditor()
    const selection = window.getSelection()
    if (selection && savedRangeRef.current) {
      selection.removeAllRanges()
      selection.addRange(savedRangeRef.current)
    }
    if (selection && !selection.isCollapsed) {
      document.execCommand('createLink', false, url)
    } else {
      document.execCommand(
        'insertHTML',
        false,
        `<a href="${url.replace(/"/g, '&quot;')}">${url}</a>`
      )
    }
    setLinkPopoverOpen(false)
    emitChange()
  }

  return (
    <div className="rich-editor">
      <div className="rich-editor-toolbar">
        <button
          type="button"
          className="toolbar-btn"
          title={t('rte_bold')}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => exec('bold')}
        >
          <IconBold />
        </button>
        <button
          type="button"
          className="toolbar-btn"
          title={t('rte_italic')}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => exec('italic')}
        >
          <IconItalic />
        </button>
        <button
          type="button"
          className="toolbar-btn"
          title={t('rte_underline')}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => exec('underline')}
        >
          <IconUnderline />
        </button>
        <button
          type="button"
          className="toolbar-btn"
          title={t('rte_strikethrough')}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => exec('strikeThrough')}
        >
          <IconStrikethrough />
        </button>
        <button
          type="button"
          className="toolbar-btn"
          title={t('rte_code')}
          onMouseDown={(e) => e.preventDefault()}
          onClick={applyCode}
        >
          <IconCode />
        </button>
        <button
          type="button"
          className="toolbar-btn"
          title={t('rte_add_link')}
          onMouseDown={(e) => e.preventDefault()}
          onClick={openLinkPopover}
        >
          <IconLinkChain />
        </button>
      </div>

      {linkPopoverOpen && (
        <div className="rich-editor-link-popover">
          <input
            type="text"
            placeholder={t('rte_link_placeholder')}
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                applyLink()
              }
              if (e.key === 'Escape') setLinkPopoverOpen(false)
            }}
            autoFocus
          />
          <button type="button" className="sm" onClick={applyLink}>
            {t('rte_link_add')}
          </button>
          <button type="button" className="ghost sm" onClick={() => setLinkPopoverOpen(false)}>
            {t('rte_link_cancel')}
          </button>
        </div>
      )}

      <div
        ref={editorRef}
        className="rich-editor-surface"
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        onInput={emitChange}
        onBlur={emitChange}
      />
    </div>
  )
}
