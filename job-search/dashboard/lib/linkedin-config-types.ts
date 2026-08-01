export interface BrowserConfig {
  channel: string
  backend: string
  debug_port: number
  headless: boolean
}

export interface LimitsConfig {
  max_connections: number
  min_delay_seconds: number
  max_delay_seconds: number
  pacing: { lognormal_mean: number; lognormal_sigma: number }
  idle_browse_seconds: number
  daily_cap: number
}

export interface VariantScoreMap {
  [variant: string]: number
}

export interface MatchingConfig {
  min_primary_score: number
  require_recruiter_gate: boolean
  cv_min_scores: VariantScoreMap
}

export interface TierRule {
  min_score: number
  company_signals?: string[]
}

export interface TiersConfig {
  tier_1: TierRule
  tier_2: TierRule
  tier_3: TierRule
}

export interface RecruiterMatchingConfig {
  sector_keywords: Record<string, string[]>
  outreach_exclude_terms: string[]
  track_aligned_company_terms: Record<string, string[]>
}

export interface QueryEntry {
  keywords: string
  exclude?: string[]
}

export interface SearchConfig {
  queries_by_variant: Record<string, QueryEntry[]>
}

export interface ConnectionNotesConfig {
  [variant: string]: string
}

export interface LlmConfig {
  provider: string
  model: string
  profiles: Record<string, { provider: string; model: string }>
}

export interface AutomationConfig {
  max_live_dispatch: number
  require_llm_note: boolean
}

export interface LinkedInConfig {
  linkedin_base_url: string
  browser: BrowserConfig
  limits: LimitsConfig
  matching: MatchingConfig
  tiers: TiersConfig
  recruiter_matching: RecruiterMatchingConfig
  search: SearchConfig
  connection_notes: ConnectionNotesConfig
  llm: LlmConfig
  automation: AutomationConfig
}
