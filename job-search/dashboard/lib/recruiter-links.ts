export function safeLinkedInProfileUrl(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null

  try {
    const url = new URL(value.trim())
    const hostname = url.hostname.toLowerCase()
    const isLinkedInHost = hostname === 'linkedin.com' || hostname.endsWith('.linkedin.com')
    const isProfilePath = /^\/in\/[^/]+\/?$/.test(url.pathname)

    if (
      url.protocol !== 'https:' ||
      url.username ||
      url.password ||
      url.port ||
      !isLinkedInHost ||
      !isProfilePath
    ) {
      return null
    }

    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    return null
  }
}
