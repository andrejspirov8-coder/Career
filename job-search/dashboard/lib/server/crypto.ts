/** Edge-compatible crypto utilities using Web Crypto API */

async function constantTimeEqual(a: Uint8Array, b: Uint8Array): Promise<boolean> {
  if (a.length !== b.length) return false
  let result = 0
  for (let i = 0; i < a.length; i++) {
    result |= a[i] ^ b[i]
  }
  return result === 0
}

export async function safeStringEqual(expected: string, candidate: string | null): Promise<boolean> {
  if (!expected || !candidate) return false
  const encoder = new TextEncoder()
  const expectedBuffer = new TextEncoder().encode(expected)
  const candidateBuffer = new TextEncoder().encode(candidate)
  
  if (expectedBuffer.length !== candidateBuffer.length) return false
  
  return constantTimeEqual(
    new Uint8Array(expectedBuffer),
    new Uint8Array(candidateBuffer)
  )
}

export async function isDashboardTokenAuthorized(expectedToken: string, requestToken: string | null): Promise<boolean> {
  if (!expectedToken || !requestToken) return false
  return safeStringEqual(expectedToken, requestToken)
}

// Synchronous version using a simple timing-safe comparison without node:crypto
export function safeStringEqualSync(expected: string, candidate: string | null): boolean {
  if (!expected || !candidate) return false
  if (expected.length !== candidate.length) return false
  
  let result = 0
  for (let i = 0; i < expected.length; i++) {
    result |= expected.charCodeAt(i) ^ candidate.charCodeAt(i)
  }
  return result === 0
}

export function isDashboardTokenAuthorizedSync(expectedToken: string, requestToken: string | null): boolean {
  if (!expectedToken || !requestToken) return false
  return safeStringEqualSync(expectedToken, requestToken)
}