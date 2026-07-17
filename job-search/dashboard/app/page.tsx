import Link from 'next/link'

import { getAutomationOverview, type AutomationOverview } from '../lib/automation-data'
import { getCvLibrary } from '../lib/cv-data'
import { requireDashboardPageAuth } from '../lib/dashboard-page-auth'
import { getOpportunityOverview, type OpportunityOverview, type OpportunitySummary } from '../lib/opportunity-data'
import { getDashboardOverview } from '../lib/repo-data'
import { getNotificationOverview } from '../lib/notification-data'
import type { NotificationOverview } from '../lib/notification-types'

export const dynamic = 'force-dynamic'

function latestRunSummary(automation: AutomationOverview | null) {
  const run = automation?.recent_runs[0]
  if (!run) return { title: 'Daily search has not run yet', detail: 'Start it when you are ready.', status: 'waiting' }
  if (run.kind === 'cv_build') {
    return {
      title: `CV library ${run.status.replaceAll('_', ' ')}`,
      detail: `${run.result.pdf_count || 0} PDF files checked`,
      status: run.status,
    }
  }
  return {
    title: `Daily search ${run.status.replaceAll('_', ' ')}`,
    detail: `${run.result.discovered || 0} found · ${run.result.matched || 0} scored`,
    status: run.status,
  }
}

function rowsFor(overview: OpportunityOverview, view: keyof OpportunityOverview['queues']['saved_views']) {
  const rowsById = new Map(overview.queues.all.map((row) => [row.opportunity_id, row]))
  return (overview.queues.saved_views[view] || [])
    .map((opportunityId) => rowsById.get(opportunityId))
    .filter((row): row is OpportunitySummary => Boolean(row))
}

function isToday(value?: string | null) {
  if (!value) return false
  const date = new Date(value)
  const now = new Date()
  return date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
}

function chooseNextAction({
  automation,
  opportunities,
  notifications,
}: {
  automation: AutomationOverview | null
  opportunities: OpportunityOverview
  notifications: NotificationOverview | null
}) {
  if (automation?.active_runs.length) {
    return {
      eyebrow: 'Automation is working',
      title: 'Let the current task finish',
      detail: 'You can leave this page open. Results will appear in the run history.',
      href: '/automation',
      label: 'Watch progress',
    }
  }
  if (notifications?.counts.urgent) {
    const urgent = notifications.counts.urgent
    return {
      eyebrow: 'Needs attention first',
      title: `Review ${urgent} urgent ${urgent === 1 ? 'update' : 'updates'}`,
      detail: 'A deadline, follow-up, source problem, or missed schedule needs a decision.',
      href: '/notifications',
      label: 'Open notification inbox',
    }
  }
  const latestSearch = automation?.recent_runs.find((run) => run.kind === 'daily_search')
  if (!latestSearch || !isToday(latestSearch.finished_at || latestSearch.requested_at)) {
    return {
      eyebrow: 'First task',
      title: 'Run today’s safe job search',
      detail: 'The app will collect, clean, score, and rank roles. It will not apply for you.',
      href: '/automation',
      label: 'Start daily search',
    }
  }
  const rolesToDecide = opportunities.counts.daily_queue || opportunities.pipeline.shortlisted
  if (rolesToDecide) {
    return {
      eyebrow: 'Best use of your time',
      title: `Review ${rolesToDecide} shortlisted ${rolesToDecide === 1 ? 'role' : 'roles'}`,
      detail: 'Decide whether to prepare an application or close each role.',
      href: '/opportunities',
      label: 'Review shortlist',
    }
  }
  if (opportunities.counts.follow_up || opportunities.counts.missing_outcome) {
    return {
      eyebrow: 'Keep records current',
      title: 'Update application follow-ups',
      detail: 'Record replies, interviews, offers, or rejections so the dashboard stays useful.',
      href: '/applications',
      label: 'Open follow-ups',
    }
  }
  return {
    eyebrow: 'You are caught up',
    title: 'No urgent job-search action remains',
    detail: 'Check again tomorrow, or browse the pipeline if you want to review older roles.',
    href: '/opportunities',
    label: 'Browse pipeline',
  }
}

export default async function Page() {
  await requireDashboardPageAuth('/')
  const [overview, automation, opportunities, notifications, cvLibrary] = await Promise.all([
    getDashboardOverview(),
    getAutomationOverview().catch(() => null),
    getOpportunityOverview(),
    getNotificationOverview().catch(() => null),
    getCvLibrary(),
  ])
  const latest = latestRunSummary(automation)
  const next = chooseNextAction({ automation, opportunities, notifications })
  const dailyQueue = rowsFor(opportunities, 'daily_queue')
  const todayRoles = dailyQueue.length ? dailyQueue : rowsFor(opportunities, 'top_5_today')
  const savedShortlist = rowsFor(opportunities, 'stage_shortlisted')
  const topRoles = (todayRoles.length ? todayRoles : savedShortlist).slice(0, 5)
  const rolesToDecide = opportunities.counts.daily_queue || opportunities.pipeline.shortlisted
  const showingSavedShortlist = !todayRoles.length && savedShortlist.length > 0
  const firstRun = !automation?.recent_runs.length && opportunities.counts.total === 0
  const latestDailySearch = automation?.recent_runs.find((run) => run.kind === 'daily_search')
  const searchDoneToday = Boolean(
    latestDailySearch
    && ['succeeded', 'partial'].includes(latestDailySearch.status)
    && isToday(latestDailySearch.finished_at || latestDailySearch.requested_at),
  )
  const followUpsToRecord = opportunities.counts.follow_up + opportunities.counts.missing_outcome
  const dailyStepsComplete = searchDoneToday
    ? 1 + Number(rolesToDecide === 0) + Number(followUpsToRecord === 0)
    : 0

  return (
    <main className="workspaceMain">
      <div className="workspaceHeading todayHeading">
        <div>
          <div className="eyebrow">{new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}</div>
          <h1>Morning briefing</h1>
          <p className="muted">A short, private list of what deserves your attention today.</p>
        </div>
        <div className="todayHeadingStatus">
          <Link className={`todayNotificationShortcut ${notifications?.counts.unread ? 'hasUnread' : ''}`} href="/notifications">
            <strong>{notifications?.counts.unread || 0}</strong>
            <span>{notifications?.counts.unread === 1 ? 'unread update' : 'unread updates'}</span>
          </Link>
          <div className={`serviceIndicator ${automation?.worker.online ? 'online' : ''}`}>
            <span aria-hidden="true" />
            <div>
              <strong>{automation?.worker.online ? 'Automation ready' : 'Automation on demand'}</strong>
              <small>Private · this Mac only</small>
            </div>
          </div>
        </div>
      </div>

      <section className="briefingHero">
        <div>
          <div className="eyebrow">{next.eyebrow}</div>
          <h2>{next.title}</h2>
          <p>{next.detail}</p>
          <div className="dailyProgress" aria-label={`${dailyStepsComplete} of 3 daily steps complete`}>
            <div><span>Daily routine</span><strong>{dailyStepsComplete}/3 complete</strong></div>
            <div className="dailyProgressTrack" aria-hidden="true">
              <span style={{ width: `${Math.round((dailyStepsComplete / 3) * 100)}%` }} />
            </div>
          </div>
        </div>
        <Link className="briefingPrimaryAction" href={next.href}>{next.label}<span aria-hidden="true">→</span></Link>
      </section>

      {firstRun ? (
        <section className="firstRunGuide" aria-labelledby="first-run-title">
          <div><div className="eyebrow">First run</div><h2 id="first-run-title">Set up your private workspace in three steps</h2></div>
          <ol>
            <li><span>1</span><div><strong>Check the CV library</strong><small>Confirm all 12 PDFs open correctly.</small></div></li>
            <li><span>2</span><div><strong>Review job sources</strong><small>Settings are pre-filled and stay local.</small></div></li>
            <li><span>3</span><div><strong>Run the daily search</strong><small>The first results will appear in Opportunities.</small></div></li>
          </ol>
        </section>
      ) : null}

      <section className="briefingChecklist" aria-label="Today at a glance">
        <BriefingItem
          label="Daily search"
          value={latest.title}
          detail={latest.detail}
          state={latest.status}
          href="/automation"
        />
        <BriefingItem
          label="Roles to decide"
          value={String(rolesToDecide)}
          detail={showingSavedShortlist ? 'Saved shortlist waiting' : `${opportunities.counts.needs_review} more in review`}
          state={rolesToDecide ? 'attention' : 'succeeded'}
          href="/opportunities"
        />
        <BriefingItem
          label="Application follow-ups"
          value={String(followUpsToRecord)}
          detail={`${overview.counts.applicationRows} applications logged`}
          state={followUpsToRecord ? 'attention' : 'succeeded'}
          href="/applications"
        />
        <BriefingItem
          label="CV library"
          value={`${cvLibrary.counts.readyPdfs}/${cvLibrary.counts.expectedPdfs}`}
          detail="PDF files ready"
          state={cvLibrary.counts.readyPdfs === cvLibrary.counts.expectedPdfs ? 'succeeded' : 'attention'}
          href="/cvs"
        />
      </section>

      <div className="briefingGrid">
        <section className="workspacePanel briefingShortlist" aria-labelledby="shortlist-title">
          <div className="panelHeading">
            <div>
              <div className="eyebrow">Shortlist</div>
              <h2 id="shortlist-title">{showingSavedShortlist ? 'Current shortlist' : 'Top roles today'}</h2>
              <p>{showingSavedShortlist ? 'Saved roles stay here until you decide or close them.' : 'Only current, eligible, role-fit jobs appear here.'}</p>
            </div>
            <Link className="textButton" href="/opportunities">Open pipeline</Link>
          </div>
          {topRoles.length ? (
            <div className="briefingRoleList">
              {topRoles.map((role) => (
                <Link href="/opportunities" key={role.opportunity_id}>
                  <span>
                    <strong>{role.title}</strong>
                    <small>{role.company} {role.location ? `· ${role.location}` : ''}</small>
                  </span>
                  <span className="briefingRoleScore">{Number(role.match?.score || 0).toFixed(1)}</span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="emptyState">No current role passed every shortlist check. Run the daily search or review warning queues if you want to inspect why.</div>
          )}
        </section>

        <section className="workspacePanel briefingSafety" aria-labelledby="safety-title">
          <div className="panelHeading">
            <div>
              <div className="eyebrow">Guardrails</div>
              <h2 id="safety-title">Always under your control</h2>
              <p>Actions the web app will never perform silently.</p>
            </div>
          </div>
          <div className="safetyList">
            <div><span>Applications</span><strong>Manual only</strong></div>
            <div><span>LinkedIn messages</span><strong>Manual or command-line approval</strong></div>
            <div><span>Daily LinkedIn ceiling</span><strong>3 sends</strong></div>
            <div><span>Dashboard access</span><strong>Local browser only</strong></div>
          </div>
          <Link className="buttonLink" href="/settings">Open settings and privacy</Link>
        </section>
      </div>
    </main>
  )
}

function BriefingItem({
  label,
  value,
  detail,
  state,
  href,
}: {
  label: string
  value: string
  detail: string
  state: string
  href: string
}) {
  return (
    <Link href={href}>
      <span className={`statusDot status-${state}`} aria-hidden="true" />
      <span><small>{label}</small><strong>{value}</strong><em>{detail}</em></span>
    </Link>
  )
}
