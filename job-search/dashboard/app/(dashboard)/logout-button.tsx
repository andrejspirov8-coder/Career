'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'

export default function LogoutButton() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)

  async function logout() {
    if (busy) return
    setBusy(true)
    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'x-career-dashboard-action': 'logout' },
        cache: 'no-store',
      })
      if (!response.ok) throw new Error('Logout failed.')
      router.replace('/login')
      router.refresh()
    } catch {
      setBusy(false)
    }
  }

  return (
    <button
      aria-label="Lock dashboard"
      className="navLockButton"
      disabled={busy}
      onClick={() => void logout()}
      type="button"
    >
      {busy ? 'Locking…' : 'Lock'}
    </button>
  )
}
