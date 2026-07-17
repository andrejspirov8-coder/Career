import { requireDashboardPageAuth } from '../../lib/dashboard-page-auth'
import { getOpportunityOverview } from '../../lib/opportunity-data'
import OpportunityConsole from './opportunity-console'

export const dynamic = 'force-dynamic'

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  await requireDashboardPageAuth('/opportunities')
  const [overview, params] = await Promise.all([getOpportunityOverview(), searchParams])

  const firstValue = (value: string | string[] | undefined) => typeof value === 'string' ? value : ''

  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Manual applications · local data</div>
          <h1>Opportunities</h1>
          <p className="muted">Move each suitable role from review to application and follow-up.</p>
        </div>
        <div className="muted small">Updated {new Date(overview.generated_at).toLocaleString()}</div>
      </div>
      <OpportunityConsole
        initialOverview={overview}
        initialUiState={{
          view: firstValue(params.view),
          opportunity: firstValue(params.opportunity),
          query: firstValue(params.q),
          sourceKind: firstValue(params.source),
          variant: firstValue(params.cv),
          status: firstValue(params.status),
          risk: firstValue(params.risk),
          page: firstValue(params.page),
        }}
      />
    </main>
  )
}
