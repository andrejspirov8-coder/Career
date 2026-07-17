import { requireDashboardPageAuth } from '../../lib/dashboard-page-auth'
import { getRecruiterOverview } from '../../lib/recruiter-data'
import RecruiterConsole from './recruiter-console'

export const dynamic = 'force-dynamic'

export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  await requireDashboardPageAuth('/recruiters')
  const [overview, params] = await Promise.all([getRecruiterOverview(), searchParams])

  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Manual LinkedIn workflow</div>
          <h1>Recruiters</h1>
          <p className="muted">Follow up first, then prepare the next exact note you will send yourself.</p>
        </div>
        <div className="muted small">Updated {new Date(overview.generated_at).toLocaleString()}</div>
      </div>
      <RecruiterConsole initialOverview={overview} initialQuery={(params.q || '').slice(0, 160)} />
    </main>
  )
}
