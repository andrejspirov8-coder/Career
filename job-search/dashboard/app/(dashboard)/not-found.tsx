import Link from 'next/link'

export default function DashboardNotFound() {
  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Not found</div>
          <h1>Page not found</h1>
          <p className="muted">This page does not exist in your Career workspace.</p>
        </div>
      </div>
      <div className="section">
        <Link className="button" href="/">
          Go to Today
        </Link>
        <Link className="button secondary" href="/opportunities" style={{ marginLeft: 8 }}>
          Browse opportunities
        </Link>
      </div>
    </main>
  )
}
