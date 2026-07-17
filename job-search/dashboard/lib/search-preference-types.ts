export const workArrangementValues = ['on_site', 'hybrid', 'remote_lithuania', 'remote_eu'] as const
export type WorkArrangement = (typeof workArrangementValues)[number]

export type SearchPreferences = {
  schema: 'career_search_preferences_v1'
  target_roles: string[]
  priority_locations: string[]
  work_arrangements: WorkArrangement[]
  minimum_salary_eur_monthly: number | null
  excluded_keywords: string[]
  excluded_companies: string[]
  daily_queue_size: number
  updated_at: string
}

export type PreferenceSuggestion = {
  kind: 'add_excluded_company' | 'add_excluded_keyword'
  value: string
  label: string
}
