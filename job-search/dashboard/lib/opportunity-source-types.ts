export interface RoleTrack {
  name: string
  weight: number
  keywords: string[]
}

export interface LlmScoringConfig {
  enabled: boolean
  llm_weight: number
  min_score_to_llm: number
  max_jobs_per_run: number
  agent: { model: string }
}

export interface LivenessConfig {
  max_page_checks: number
  network_timeout_seconds: number
}

export interface CompanyWatchlistEntry {
  name: string
  careers_url: string
}

export interface OfficialCareerEntry {
  provider: string
  company: string
  listing_url: string
}

export interface AtsProviderEntry {
  provider: string
  company: string
  board_token?: string
  company_slug?: string
  job_board_name?: string
  max_posts: number
  enabled?: boolean
}

export interface LinkedInSourceConfig {
  enabled: boolean
  mode: string
  base_url: string
  location: string
  posted_within_hours: number
  max_queries: number
  max_results_per_query: number
  max_jobs: number
  pages: number
  max_detail_pages: number
  timeout_ms: number
  settle_ms: number
  browser_channel: string
  headed: boolean
  profile_dir: string
  queries: string[]
}

export interface ScoredSourceConfig {
  enabled: boolean
  [key: string]: unknown
}

export interface AtsSourceConfig extends ScoredSourceConfig {
  network_timeout_seconds: number
  providers: AtsProviderEntry[]
  fixtures: string[]
}

export interface CompanyWatchlistConfig extends ScoredSourceConfig {
  companies: CompanyWatchlistEntry[]
}

export interface OfficialCareersConfig extends ScoredSourceConfig {
  network_timeout_seconds: number
  max_page_chars: number
  max_rows_per_company: number
  companies: OfficialCareerEntry[]
}

export interface OpportunitySources {
  inbox: ScoredSourceConfig & { path?: string; exclude_name_patterns?: string[] }
  company_watchlist: CompanyWatchlistConfig
  official_company_careers: OfficialCareersConfig
  cvmarket_rss: ScoredSourceConfig & { feed_url?: string; locations?: string[] }
  cvonline_public_search: ScoredSourceConfig & { queries?: string[] }
  cvbankas_public_search: ScoredSourceConfig & { queries?: string[] }
  workinlithuania_public_search: ScoredSourceConfig
  uzt_open_data: ScoredSourceConfig
  ats: AtsSourceConfig
  linkedin: LinkedInSourceConfig
  job_board: ScoredSourceConfig
  web_search: ScoredSourceConfig
}

export interface OpportunityConfig {
  opportunities: {
    geography: {
      default_regions: string[]
    }
    scoring: {
      priority_regions: string[]
      role_tracks: RoleTrack[]
    }
    llm_scoring: LlmScoringConfig
    liveness: LivenessConfig
    sources: OpportunitySources
  }
}
