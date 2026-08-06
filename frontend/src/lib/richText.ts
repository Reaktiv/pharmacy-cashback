/** Client-side mirror of apps/broadcasts/sanitizer.py — used only for the
 * live preview and character counter. The server re-sanitizes on save/send
 * regardless (never trust client output), so this just has to be a
 * reasonably faithful approximation of what the server will actually do. */

const ALLOWED_TAGS = new Set(['B', 'I', 'U', 'S', 'CODE', 'PRE', 'A'])
const TAG_ALIASES: Record<string, string> = { STRONG: 'B', EM: 'I', STRIKE: 'S', DEL: 'S' }
const BLOCK_TAGS = new Set(['DIV', 'P', 'BR', 'LI', 'TR'])
const DROP_CONTENT_TAGS = new Set(['SCRIPT', 'STYLE'])

function escapeText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function isSafeHref(href: string): boolean {
  try {
    const url = new URL(href, window.location.origin)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function sanitizeRichTextHtml(rawHtml: string): string {
  const doc = new DOMParser().parseFromString(rawHtml, 'text/html')
  const out: string[] = []

  const newline = () => {
    if (out.length && !out[out.length - 1].endsWith('\n')) out.push('\n')
  }

  const walkChildren = (node: Node) => {
    node.childNodes.forEach(walk)
  }

  const walk = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      out.push(escapeText(node.textContent || ''))
      return
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return

    const el = node as HTMLElement
    const tag = el.tagName

    if (DROP_CONTENT_TAGS.has(tag)) return
    if (tag === 'BR') {
      newline()
      return
    }
    if (BLOCK_TAGS.has(tag)) {
      newline()
      walkChildren(el)
      return
    }

    const canonical = TAG_ALIASES[tag] || tag
    if (!ALLOWED_TAGS.has(canonical)) {
      walkChildren(el) // unknown tag: unwrap, keep its text
      return
    }

    if (canonical === 'A') {
      const href = el.getAttribute('href') || ''
      if (!isSafeHref(href)) {
        walkChildren(el) // not a real link — render as plain text
        return
      }
      out.push(`<a href="${href.replace(/"/g, '&quot;')}">`)
      walkChildren(el)
      out.push('</a>')
      return
    }

    const lower = canonical.toLowerCase()
    out.push(`<${lower}>`)
    walkChildren(el)
    out.push(`</${lower}>`)
  }

  walkChildren(doc.body)
  return out
    .join('')
    .replace(/\n{2,}/g, '\n')
    .replace(/^\n+|\n+$/g, '')
}

/** JS strings are already UTF-16 internally, so `.length` already counts
 * code units the same way Telegram does (surrogate pairs count as 2) —
 * no extra encoding step needed, unlike Python. */
export function plainTextLength(html: string): number {
  const doc = new DOMParser().parseFromString(html, 'text/html')
  return (doc.body.textContent || '').length
}

export function renderBroadcastMessageHtml(title: string, bodyHtml: string): string {
  const header = title ? `<b>${escapeText(title)}</b>` : ''
  if (header && bodyHtml) return `${header}\n\n${bodyHtml}`
  return header || bodyHtml
}
