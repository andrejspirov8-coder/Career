'use client'

import { useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'

export function SignupForm() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const handleSubmit = useCallback(async () => {
    setError(null)

    if (!email.includes('@')) {
      setError('Please enter a valid email address')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }

    setBusy(true)
    try {
      const response = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = (await response.json()) as { ok?: boolean; error?: string }
      if (!response.ok || !data.ok) {
        setError(data.error || 'Signup failed')
        return
      }
      router.push('/login?created=1')
    } catch {
      setError('Signup request failed')
    } finally {
      setBusy(false)
    }
  }, [email, password, confirm, router])

  return (
    <div className="card loginCard">
      <div>
        <div className="badge">New account</div>
        <h1>Create Account</h1>
        <p className="muted">Set up an email and password to sign in without the dashboard token.</p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          handleSubmit()
        }}
      >
        <label>
          Email
          <input
            autoComplete="email"
            autoFocus
            disabled={busy}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            type="email"
            value={email}
          />
        </label>
        <label>
          Password
          <input
            autoComplete="new-password"
            disabled={busy}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="At least 8 characters"
            type="password"
            value={password}
          />
        </label>
        <label>
          Confirm password
          <input
            autoComplete="new-password"
            disabled={busy}
            onChange={(event) => setConfirm(event.target.value)}
            placeholder="Repeat your password"
            type="password"
            value={confirm}
          />
        </label>
        {error ? <div className="banner" role="alert">{error}</div> : null}
        <button className="button" disabled={busy || !email || !password || !confirm} type="submit">
          {busy ? 'Creating account...' : 'Create account'}
        </button>
        <p className="signup-link">
          Already have an account? <a href="/login">Sign in</a>
        </p>
      </form>
    </div>
  )
}
