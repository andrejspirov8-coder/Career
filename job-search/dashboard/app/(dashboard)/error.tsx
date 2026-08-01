'use client'

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Error</div>
          <h1>Something went wrong</h1>
          <p className="muted">{error.message || 'This page could not be loaded.'}</p>
        </div>
      </div>
      <div className="section">
        <button className="button" type="button" onClick={reset}>
          Try again
        </button>
        <a className="button secondary" href="/" style={{ marginLeft: 8 }}>
          Go to Today
        </a>
      </div>
    </main>
  )
}
