import { getApplicationWorkspaceOverview } from '@/lib/application-data'
import { requireDashboardPageAuth } from '@/lib/dashboard-page-auth'
import { isOpportunityId } from '@/lib/opportunity-shared'
import { getLocalDraftingStatus } from '@/lib/local-drafting'
import type { LocalDraftingStatus } from '@/lib/local-drafting-types'
import ApplicationWorkspaceConsole from './application-workspace-console'

export const dynamic = 'force-dynamic'

function unavailableDraftingStatus(): LocalDraftingStatus {
  return {
    schema: 'career_local_drafting_status_v1',
    enabled: false,
    model: 'qwen3.5:35b-a3b-fast',
    provider: 'local_ollama',
    network_scope: '127.0.0.1 only',
    dashboard_stores_prompts: false,
    automatic_actions: false,
    ollama: { online: false, models: [], base_url: 'http://127.0.0.1:11434', message: 'Local drafting status is unavailable.' },
  }
}

export default async function ApplicationsPage({
  searchParams,
}: {
  searchParams: Promise<{ opportunity?: string }>
}) {
  await requireDashboardPageAuth('/applications')
  const [overview, params, draftingStatus] = await Promise.all([
    getApplicationWorkspaceOverview(),
    searchParams,
    getLocalDraftingStatus().catch(unavailableDraftingStatus),
  ])
  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Manual submission workspace</div>
          <h1>Applications</h1>
          <p className="muted">Keep the chosen CV, preparation files, dates, reminders, and outcomes together.</p>
        </div>
        <a className="buttonLink" href="/api/applications/calendar">Add dates to calendar</a>
      </div>
      <ApplicationWorkspaceConsole
        initialOverview={overview}
        initialOpportunity={isOpportunityId(params.opportunity) ? params.opportunity : ''}
        draftingStatus={draftingStatus}
      />
    </main>
  )
}
