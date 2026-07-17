export function safeExternalHttpUrl(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim() || value.length > 2048) return null

  try {
    const url = new URL(value.trim())
    if (
      (url.protocol !== 'https:' && url.protocol !== 'http:') ||
      url.username ||
      url.password
    ) {
      return null
    }
    return url.toString()
  } catch {
    return null
  }
}
