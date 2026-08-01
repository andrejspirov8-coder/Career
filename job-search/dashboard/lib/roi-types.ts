export interface RoiSourceStat {
  source: string
  submitted: number
  interviews: number
  interview_rate: number
}

export interface WeeklyRoiSummary {
  schema: 'career_weekly_roi_summary_v1'
  generated_at: string
  applications: {
    submitted: number
    interviews: number
    interview_rate: number
    missing_outcome: number
    best_sources: RoiSourceStat[]
    worst_sources: RoiSourceStat[]
  }
  recruiters: {
    sent: number
    missing_accepted_at: number
    missing_reply_at: number
    missing_interview_at: number
  }
  next_roi_action: string
}
