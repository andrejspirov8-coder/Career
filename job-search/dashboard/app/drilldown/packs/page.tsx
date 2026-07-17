import Link from 'next/link'
import { requireDashboardPageAuth } from '../../../lib/dashboard-page-auth'
import { getDashboardOverview } from '../../../lib/repo-data'

export const dynamic = 'force-dynamic'

export default async function Page() {
  await requireDashboardPageAuth('/drilldown/packs')
  const overview = await getDashboardOverview()
  return (
    <main>
      <BackLink />
      <h1>Packs drill-down</h1>
      <p className="muted">Recent pack directories and the matching summary.</p>
      <div className="card">
        {overview.recentPacks.length ? overview.recentPacks.map((item) => (
          <div className="artifactRow" key={item.path}><span>{item.label}</span><span className="muted">{item.path}</span></div>
        )) : <p className="muted">No packs generated yet.</p>}
      </div>
    </main>
  )
}
function BackLink(){ return <p><Link href="/">← Back</Link></p> }
