import Link from 'next/link'

import { getCareerAnalytics } from '@/lib/analytics-data'
import type { AnalyticsPerformanceRow, CareerAnalyticsOverview } from '@/lib/analytics-types'
import { requireDashboardPageAuth } from '@/lib/dashboard-page-auth'

export const dynamic = 'force-dynamic'

function percentage(value: number) {
  return `${Math.round(Math.max(0, value) * 100)}%`
}

function label(value: string) {
  return value.replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function unavailableAnalytics(): CareerAnalyticsOverview {
  return {
    schema: 'career_analytics_overview_v1',
    generated_at: new Date().toISOString(),
    funnel: { logged: 0, submitted: 0, responses: 0, screenings_or_better: 0, interviews_or_better: 0, offers: 0, rejected: 0, withdrawn: 0, response_rate: 0, interview_rate: 0, offer_rate: 0, avg_response_days: null },
    data_quality: { missing_outcome: 0, outcome_coverage_rate: 0, reliable_sample: false, minimum_reliable_sample: 10 },
    by_source: [],
    by_variant: [],
    by_tailoring: [],
    by_match_score: [],
    outcome_history: { events: 0, invalid_records: 0, transitions: [] },
    weekly_trend: [],
    recruiters: { profiles_logged: 0, sent: 0, accepted: 0, replies: 0, interviews: 0, accept_rate: 0, reply_rate: 0, interview_rate: 0, sample_status: 'insufficient' },
    recommendations: [{ priority: 'normal', title: 'Insights are unavailable', message: 'Check the local service, then refresh this page.' }],
    privacy: { aggregate_only: true, includes_descriptions: false, message: 'Private descriptions and notes are excluded.' },
  }
}

export default async function InsightsPage() {
  await requireDashboardPageAuth('/insights')
  const analytics = await getCareerAnalytics().catch(unavailableAnalytics)
  const maxWeek = Math.max(1, ...analytics.weekly_trend.map((week) => week.submitted))
  const funnel = [
    ['Submitted', analytics.funnel.submitted],
    ['Responded', analytics.funnel.responses],
    ['Screening+', analytics.funnel.screenings_or_better],
    ['Interview+', analytics.funnel.interviews_or_better],
    ['Offers', analytics.funnel.offers],
  ] as const

  return (
    <main className="workspaceMain">
      <div className="workspaceHeading">
        <div>
          <div className="eyebrow">Outcome learning</div>
          <h1>Insights</h1>
          <p className="muted">See what is converting, what is too early to judge, and which outcomes need an update.</p>
        </div>
        <div className={`sampleIndicator ${analytics.data_quality.reliable_sample ? 'ready' : ''}`}>
          <strong>{analytics.data_quality.reliable_sample ? 'Reliable sample reached' : 'Early signal only'}</strong>
          <small>{analytics.funnel.submitted}/{analytics.data_quality.minimum_reliable_sample} applications recorded</small>
        </div>
      </div>

      <section className="insightRecommendations" aria-label="Recommended next actions">
        {analytics.recommendations.map((recommendation) => (
          <div className={`insightRecommendation ${recommendation.priority}`} key={`${recommendation.priority}-${recommendation.title}`}>
            <span>{recommendation.priority}</span>
            <strong>{recommendation.title}</strong>
            <p>{recommendation.message}</p>
          </div>
        ))}
      </section>

      <section className="workspacePanel funnelPanel" aria-labelledby="application-funnel-title">
        <div className="panelHeading">
          <div><div className="eyebrow">Application funnel</div><h2 id="application-funnel-title">Where applications are progressing</h2><p>Each step is measured from manually logged outcomes.</p></div>
          <Link className="textButton" href="/applications">Update outcomes</Link>
        </div>
        <div className="funnelSteps">
          {funnel.map(([name, value]) => (
            <div key={name}>
              <span style={{ width: `${analytics.funnel.submitted ? Math.max(4, (value / analytics.funnel.submitted) * 100) : 4}%` }} />
              <strong>{value}</strong>
              <small>{name}</small>
            </div>
          ))}
        </div>
        <div className="insightMetricBand">
          <Metric label="Response rate" value={percentage(analytics.funnel.response_rate)} />
          <Metric label="Interview rate" value={percentage(analytics.funnel.interview_rate)} />
          <Metric label="Offer rate" value={percentage(analytics.funnel.offer_rate)} />
          <Metric label="Average response" value={analytics.funnel.avg_response_days == null ? 'Not enough data' : `${analytics.funnel.avg_response_days.toFixed(1)} days`} />
        </div>
      </section>

      <div className="insightsGrid">
        <PerformancePanel title="Sources" subtitle="Which channels deserve time" rows={analytics.by_source} />
        <PerformancePanel title="CV variants" subtitle="Which positioning is earning interviews" rows={analytics.by_variant} />
      </div>

      <div className="insightsGrid">
        <PerformancePanel title="Tailoring effect" subtitle="Whether tailored CVs are converting better" rows={analytics.by_tailoring} />
        <PerformancePanel title="Match-score signal" subtitle="Whether stronger matches are converting better" rows={analytics.by_match_score} />
      </div>

      <div className="insightsGrid">
        <section className="workspacePanel trendPanel">
          <div className="panelHeading"><div><div className="eyebrow">Eight weeks</div><h2>Application rhythm</h2><p>Submitted applications and interview outcomes by week.</p></div></div>
          <div className="weeklyBars" aria-label="Eight-week application activity">
            {analytics.weekly_trend.map((week) => (
              <div key={week.week_start}>
                <span className="weekBarTrack"><i style={{ height: `${Math.max(3, (week.submitted / maxWeek) * 100)}%` }} /><em style={{ height: `${Math.max(0, (week.interviews / maxWeek) * 100)}%` }} /></span>
                <strong>{week.submitted}</strong>
                <small>{new Date(`${week.week_start}T00:00:00Z`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</small>
              </div>
            ))}
          </div>
          <div className="chartLegend"><span><i /> Applications</span><span><em /> Interviews</span></div>
        </section>

        <section className="workspacePanel recruiterInsightPanel">
          <div className="panelHeading"><div><div className="eyebrow">Human network</div><h2>Recruiter outreach</h2><p>Manual LinkedIn outcomes only.</p></div><span className={`statusPill sample-${analytics.recruiters.sample_status}`}>{analytics.recruiters.sample_status}</span></div>
          <div className="recruiterInsightGrid">
            <Metric label="Sent" value={String(analytics.recruiters.sent)} />
            <Metric label="Accepted" value={`${analytics.recruiters.accepted} · ${percentage(analytics.recruiters.accept_rate)}`} />
            <Metric label="Replies" value={`${analytics.recruiters.replies} · ${percentage(analytics.recruiters.reply_rate)}`} />
            <Metric label="Interviews" value={`${analytics.recruiters.interviews} · ${percentage(analytics.recruiters.interview_rate)}`} />
          </div>
          <Link className="buttonLink" href="/recruiters">Update recruiter outcomes</Link>
        </section>
      </div>

      <section className="workspacePanel insightQuality">
        <div><span>Outcome coverage</span><strong>{percentage(analytics.data_quality.outcome_coverage_rate)}</strong><small>{analytics.data_quality.missing_outcome} missing or still marked applied</small></div>
        <p>{analytics.privacy.message} Rates stay labelled as early until at least {analytics.data_quality.minimum_reliable_sample} applications exist. {analytics.outcome_history.events} outcome transitions are preserved for audit.{analytics.outcome_history.invalid_records ? ` ${analytics.outcome_history.invalid_records} invalid event records were ignored.` : ''}</p>
      </section>
    </main>
  )
}

function PerformancePanel({ title, subtitle, rows }: { title: string; subtitle: string; rows: AnalyticsPerformanceRow[] }) {
  return (
    <section className="workspacePanel performancePanel">
      <div className="panelHeading"><div><h2>{title}</h2><p>{subtitle}</p></div></div>
      {rows.length ? <div className="performanceRows">
        {rows.slice(0, 8).map((row) => (
          <div key={row.label}>
            <span><strong>{label(row.label)}</strong><small>{row.submitted} submitted · {row.interviews} interview{row.interviews === 1 ? '' : 's'}</small></span>
            <span><strong>{percentage(row.interview_rate)}</strong><small>{row.sample_status === 'ready' ? 'Reliable sample' : row.needed_for_reliable_sample ? `${row.needed_for_reliable_sample} more needed` : 'Early signal'}</small></span>
          </div>
        ))}
      </div> : <div className="emptyState">Log manual application outcomes to compare {title.toLowerCase()}.</div>}
    </section>
  )
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return <div><span>{metricLabel}</span><strong>{value}</strong></div>
}
