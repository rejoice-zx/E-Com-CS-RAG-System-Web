const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:'])

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function decodeHtmlEntities(value: string): string {
  if (typeof window === 'undefined') return value
  const textarea = document.createElement('textarea')
  textarea.innerHTML = value
  return textarea.value
}

function sanitizeHref(rawHref: string): string | null {
  const decoded = decodeHtmlEntities(rawHref.trim())
  if (!decoded) return null

  if (decoded.startsWith('/') || decoded.startsWith('#') || decoded.startsWith('?')) {
    return escapeHtml(decoded)
  }

  try {
    const parsed = new URL(decoded, window.location.origin)
    if (SAFE_PROTOCOLS.has(parsed.protocol)) {
      return escapeHtml(decoded)
    }
  } catch {
    return null
  }

  return null
}

export function renderSafeMarkdown(content: string): string {
  if (!content) return ''

  const escaped = escapeHtml(content.trim())

  return escaped
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang: string, code: string) => {
      const language = lang || 'text'
      return `<pre><code class="language-${language}">${code}</code></pre>`
    })
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label: string, href: string) => {
      const safeHref = sanitizeHref(href)
      if (!safeHref) return label
      return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer nofollow">${
        label
      }</a>`
    })
    .replace(/\n/g, '<br>')
}
