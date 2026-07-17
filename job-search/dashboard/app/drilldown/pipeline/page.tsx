import Link from 'next/link'
import { requireDashboardPageAuth } from '../../../lib/dashboard-page-auth'
import { getDashboardOverview } from '../../../lib/repo-data'

export const dynamic = 'force-dynamic'

export default async function Page() {
  await requireDashboardPageAuth('/drilldown/pipeline')
  const overview = await getDashboardOverview()
  return (
    <main>
      <BackLink />
      <h1>Pipeline drill-down</h1>
      <p className="muted">State files written by recruiter and discovery workflows.</p>
      <div className="card">{overview.recentPipelineFiles.map((item) => (<div className="artifactRow" key={item.path}><span>{item.label}</span><span className="muted">{item.path}</span></div>))}</div>
    </main>
  )
}
function BackLink(){ return <p><Link href="/">← Back</Link></p> }
