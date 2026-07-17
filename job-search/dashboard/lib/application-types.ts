import type { OpportunityStage, OpportunityStatus } from './opportunity-data'

export type CoverLetterStatus = 'not_started' | 'draft' | 'ready' | 'not_needed'

export type ApplicationWorkspaceEntry = {
  opportunity_id: string
  deadline_date: string
  reminder_date: string
  next_step: string
  contact_name: string
  notes: string
  cover_letter_status: CoverLetterStatus
  cover_letter_draft: string
  follow_up_draft: string
  updated_at: string
}

export type ApplicationWorkspaceRow = ApplicationWorkspaceEntry & {
  title: string
  company: string
  location: string
  status: OpportunityStatus
  stage: OpportunityStage
  source_url: string
  fit_score: number
  cv_variant: string
  has_pack: boolean
  cv_files: {
    visual: string
    ats: string
  } | null
  pack_files: Array<{
    key: 'readme' | 'match_json' | 'keyword_gaps' | 'job_input'
    label: string
    url: string
  }>
}

export type ApplicationWorkspaceOverview = {
  schema: 'career_application_workspace_v1'
  generated_at: string
  counts: {
    active: number
    shortlisted: number
    applied: number
    follow_up: number
    due_next_7_days: number
    reminders_due: number
  }
  rows: ApplicationWorkspaceRow[]
}
