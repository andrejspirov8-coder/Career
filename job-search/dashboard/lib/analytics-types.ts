export type AnalyticsPerformanceRow = {
  label: string
  submitted: number
  responses: number
  interviews: number
  offers: number
  response_rate: number
  interview_rate: number
  avg_response_days?: number | null
  sample_status: 'ready' | 'early' | 'insufficient'
  needed_for_reliable_sample: number
}

export type CareerAnalyticsOverview = {
  schema: 'career_analytics_overview_v1'
  generated_at: string
  funnel: {
    logged: number
    submitted: number
    responses: number
    screenings_or_better: number
    interviews_or_better: number
    offers: number
    rejected: number
    withdrawn: number
    response_rate: number
    interview_rate: number
    offer_rate: number
    avg_response_days?: number | null
  }
  data_quality: {
    missing_outcome: number
    outcome_coverage_rate: number
    reliable_sample: boolean
    minimum_reliable_sample: number
  }
  by_source: AnalyticsPerformanceRow[]
  by_variant: AnalyticsPerformanceRow[]
  weekly_trend: Array<{ week_start: string; submitted: number; interviews: number }>
  recruiters: {
    profiles_logged: number
    sent: number
    accepted: number
    replies: number
    interviews: number
    accept_rate: number
    reply_rate: number
    interview_rate: number
    sample_status: 'ready' | 'early' | 'insufficient'
  }
  recommendations: Array<{
    priority: 'high' | 'normal' | 'opportunity'
    title: string
    message: string
  }>
  privacy: {
    aggregate_only: true
    includes_descriptions: false
    message: string
  }
}
