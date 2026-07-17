import { requireDashboardPageAuth } from '../../lib/dashboard-page-auth'
import { getAutomationOverview, type AutomationOverview } from '../../lib/automation-data'
import AutomationConsole from './automation-console'

export const dynamic = 'force-dynamic'

function unavailableOverview(message: string): AutomationOverview {
  return {
    schema: 'career_automation_overview_v1',
    generated_at: new Date().toISOString(),
    settings: {
      schedule_enabled: false,
      schedule_time: '08:00',
      timezone: 'Europe/Vilnius',
      updated_at: new Date().toISOString(),
    },
    worker: { online: false, status: 'unavailable' },
    counts: {
      queued: 0,
      running: 0,
      cancel_requested: 0,
      succeeded: 0,
      partial: 0,
      failed: 0,
      cancelled: 0,
    },
    active_runs: [],
    recent_runs: [],
    source_health: {
      overall_status: 'not_run',
      last_checked_at: null,
      age_hours: null,
      sources: [],
      message: 'Run the daily search once to check each source.',
    },
    available_actions: ['daily_search', 'cv_build'],
    safety: {
      scheduled_linkedin_enabled: false,
      live_linkedin_dispatch_enabled: false,
      message,
    },
  }
}

export default async function AutomationPage() {
  await requireDashboardPageAuth('/automation')
  let overview: AutomationOverview
  try {
    overview = await getAutomationOverview()
  } catch {
    overview = unavailableOverview('The local automation helper is unavailable. Check the service and try again.')
  }
  return (
    <main className="workspaceMain">
      <AutomationConsole initialOverview={overview} />
    </main>
  )
}
