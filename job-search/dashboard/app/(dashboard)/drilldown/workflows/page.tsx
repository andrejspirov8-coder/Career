import Link from 'next/link'
import { requireDashboardPageAuth } from '@/lib/dashboard-page-auth'
import { getDashboardOverview } from '@/lib/repo-data'

export const dynamic = 'force-dynamic'

export default async function Page() {
  await requireDashboardPageAuth('/drilldown/workflows')
  const overview = await getDashboardOverview()
  return (
    <main>
      <BackLink />
      <h1>Workflow drill-down</h1>
      <p className="muted">Operational commands and their current availability.</p>
      <div className="card">{overview.workflowChecks.map((item) => (<div className="artifactRow" key={item.label}><span>{item.label}</span><span className="muted">{item.available ? 'ready' : 'missing'}</span></div>))}</div>
    </main>
  )
}
function BackLink(){ return <p><Link href="/">← Back</Link></p> }
