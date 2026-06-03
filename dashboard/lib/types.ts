export interface Profile {
  name: string;
  company: string;
  headline: string;
  profile_url: string;
  variant_slug_best: string;
  primary_score: number;
  confidence: 'clear_winner' | 'tie_review';
  recruiter_gate_ok: boolean;
  top_signals: string;
  tier_candidate: 'tier_1' | 'tier_2' | 'tier_3' | 'tier_rest';
  created_at?: string;
}

export interface ScoutData {
  total_profiles: number;
  tier_1_count: number;
  tier_2_count: number;
  tier_3_count: number;
  tier_rest_count: number;
  profiles: Profile[];
  last_updated: string;
}

export interface TierStats {
  tier: string;
  sent: number;
  responses: number;
  response_rate: number;
  avg_score: number;
}

export interface CompanyStats {
  company: string;
  sent: number;
  responses: number;
  response_rate: number;
}

export interface Analytics {
  total_sent: number;
  total_responses: number;
  overall_response_rate: number;
  tier_stats: TierStats[];
  company_stats: CompanyStats[];
  score_distribution: Record<string, number>;
  confidence_stats: Record<string, { sent: number; responses: number; response_rate: number }>;
  rows_analyzed: number;
  last_updated: string;
}

export interface DashboardState {
  scoutData: ScoutData | null;
  analytics: Analytics | null;
  loading: boolean;
  error: string | null;
  lastUpdated: string | null;
}
