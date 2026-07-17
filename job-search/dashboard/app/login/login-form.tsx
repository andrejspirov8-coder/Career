'use client'

import { FormEvent, useState } from 'react'

export default function LoginForm({ nextPath, configured }: { nextPath: string; configured: boolean }) {
  const [token, setToken] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState(configured ? '' : 'CAREER_DASHBOARD_TOKEN is not configured on the server.')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!configured || busy) return

    setBusy(true)
    setError('')
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, remember }),
      })
      const data = (await response.json()) as { ok?: boolean; error?: string }
      if (!response.ok || !data.ok) {
        setError(data.error || `Login failed with HTTP ${response.status}.`)
        return
      }
      window.location.assign(nextPath)
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'Login failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card loginCard" onSubmit={submit}>
      <div>
        <div className="badge">Local access</div>
        <h1>Career Dashboard</h1>
        <p className="muted">Enter the local dashboard token once. A protected cookie can keep this browser signed in across server restarts.</p>
      </div>
      <label>
        Dashboard token
        <input
          autoComplete="current-password"
          autoFocus
          disabled={!configured || busy}
          onChange={(event) => setToken(event.target.value)}
          placeholder="CAREER_DASHBOARD_TOKEN"
          type="password"
          value={token}
        />
      </label>
      <label className="loginRemember">
        <input
          checked={remember}
          disabled={!configured || busy}
          onChange={(event) => setRemember(event.target.checked)}
          type="checkbox"
        />
        <span>
          Remember this browser for 30 days
          <small>Uncheck this to use the shorter eight-hour session.</small>
        </span>
      </label>
      {error ? <div className="banner" role="alert">{error}</div> : null}
      <button className="button" disabled={!configured || busy || !token.trim()} type="submit">
        {busy ? 'Checking...' : 'Unlock dashboard'}
      </button>
    </form>
  )
}
