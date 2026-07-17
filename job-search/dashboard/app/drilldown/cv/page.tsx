import Link from 'next/link'
import { requireDashboardPageAuth } from '../../../lib/dashboard-page-auth'
import { getDashboardOverview } from '../../../lib/repo-data'

export const dynamic = 'force-dynamic'

export default async function Page() {
  await requireDashboardPageAuth('/drilldown/cv')
  const overview = await getDashboardOverview()
  return (
    <main>
      <BackLink />
      <h1>CV drill-down</h1>
      <p className="muted">Variant count and the key source file.</p>
      <section className="grid">
        <div className="card"><h3>Variants</h3><div className="kpi">{overview.counts.cvVariants}</div></div>
        <div className="card"><h3>Variant source</h3><p className="muted">cv/variant_profiles.yaml</p></div>
      </section>
    </main>
  )
}
function BackLink(){ return <p><Link href="/">← Back</Link></p> }
