export interface OpportunityCommandPayload {
  ok: boolean;
  data?: {
    count?: number;
    persisted?: number;
    dry_run?: boolean;
    expired?: number;
    discovered?: number;
    matched?: number;
    partial?: boolean;
    new_live_jobs?: OpportunityRow[];
    source_results?: Array<{
      source: string;
      status: string;
      complete: boolean;
      error?: string;
    }>;
    review_queue?: {
      fresh_live_matches?: number;
      top_5_today?: number;
      apply_today?: number;
      needs_cv_tailoring?: number;
      missing_outcome?: number;
      follow_up?: number;
    };
    opportunities?: OpportunityRow[];
  };
  error?: string;
}

export interface OpportunityOverview {
  counts: {
    total: number;
    fresh_live_matches?: number;
    new_today?: number;
    updated_roles?: number;
    closing_soon?: number;
    top_5_today?: number;
    apply_today?: number;
    best_europe_matches?: number;
    apply_ready?: number;
    missing_outcome?: number;
    follow_up?: number;
    risk_flags?: number;
  };
  queues?: {
    saved_views?: Record<string, OpportunityRow[]>;
  };
  safe_actions?: string[];
}

export interface OpportunityRow {
  opportunity_id: string;
  source: string;
  source_url: string;
  source_kind: string;
  title: string;
  company: string;
  location: string;
  remote_policy?: string;
  location_eligibility?: string;
  salary_text?: string;
  deadline?: string;
  status: string;
  next_action: string;
  evidence?: {
    risk_flags?: string[];
    cv_fit_evidence?: string[];
  };
  match?: {
    score?: number;
    fit_score?: number;
    cv_score?: number;
    location_score?: number;
    role_track_score?: number;
    source_score?: number;
    role_track?: string;
    best_variant?: string;
    confidence?: string;
    missing_keywords?: string[];
    explanation?: Record<string, string>;
  } | null;
  pack?: {
    pack_id?: string;
    pack_dir?: string;
  } | null;
}

export const opportunityViewOrder = [
  "fresh_live_matches",
  "top_5_today",
  "new_today",
  "updated_roles",
  "closing_soon",
  "apply_today",
  "best_europe_matches",
  "best_matches",
  "needs_review",
  "needs_cv_tailoring",
  "apply_ready",
  "likely_duplicate",
  "likely_expired",
  "missing_outcome",
  "follow_up",
  "risk_flags",
] as const;

export const opportunityViewLabels: Record<(typeof opportunityViewOrder)[number], string> = {
  fresh_live_matches: "Fresh Live Matches",
  new_today: "New Today",
  updated_roles: "Updated Roles",
  closing_soon: "Closing Soon",
  top_5_today: "Top 5 Today",
  apply_today: "Apply Today",
  best_europe_matches: "Best Europe Matches",
  best_matches: "Best Matches",
  needs_review: "Needs Review",
  apply_ready: "Apply Ready",
  needs_cv_tailoring: "Needs CV Tailoring",
  likely_duplicate: "Likely Duplicate",
  likely_expired: "Likely Expired",
  missing_outcome: "Missing Outcome",
  follow_up: "Follow Up",
  risk_flags: "Risk Flags",
};

export function parseOpportunityCommandSummary(payload: OpportunityCommandPayload): string {
  if (!payload.ok) {
    return payload.error || "Opportunity command failed.";
  }
  if (payload.data && "discovered" in payload.data) {
    const queue = payload.data.review_queue || {};
    const failures = (payload.data.source_results || []).filter((result) => result.status === "failed").length;
    return `Discovered ${payload.data.discovered ?? 0}. Matched ${payload.data.matched ?? 0}. Fresh ${
      payload.data.new_live_jobs?.length ?? queue.fresh_live_matches ?? 0
    }, source failures ${failures}, apply today ${queue.apply_today ?? 0}, tailor CV ${
      queue.needs_cv_tailoring ?? 0
    }, missing outcome ${queue.missing_outcome ?? 0}, follow-up ${queue.follow_up ?? 0}.`;
  }
  const count = payload.data?.count ?? 0;
  const persisted = payload.data?.persisted ?? 0;
  const expired = payload.data?.expired ?? 0;
  const base =
    payload.data && "dry_run" in payload.data ? `Found ${count} opportunities.` : `Processed ${count} opportunities.`;
  const persistedText = `Persisted ${persisted}.`;
  return expired ? `${base} ${persistedText} Marked ${expired} likely closed.` : `${base} ${persistedText}`;
}

export function summarizeOpportunityOverview(overview: OpportunityOverview) {
  const safeActions = new Set(overview.safe_actions || []);
  return {
    title: `${overview.counts.total} opportunities`,
    subtitle: `${overview.counts.fresh_live_matches ?? 0} fresh live, ${
      overview.counts.apply_today ?? 0
    } apply today, ${
      overview.counts.missing_outcome ?? 0
    } missing outcome, ${overview.counts.follow_up ?? 0} follow-up`,
    hasAutoApply: safeActions.has("auto_apply"),
  };
}

export function rowsForOpportunityView(overview: OpportunityOverview | undefined, view: string): OpportunityRow[] {
  return overview?.queues?.saved_views?.[view] || [];
}

export function opportunityDetailMarkdown(row: OpportunityRow): string {
  const match = row.match || undefined;
  const riskFlags = row.evidence?.risk_flags?.length ? row.evidence.risk_flags.join(", ") : "None recorded";
  const missing = match?.missing_keywords?.length ? match.missing_keywords.join(", ") : "None recorded";
  const explanation = match?.explanation || {};
  return [
    `# ${row.title || row.company || row.opportunity_id}`,
    "",
    `**Company:** ${row.company || "-"}`,
    `**Location:** ${row.location || "-"}`,
    `**Source:** ${row.source_kind} / ${row.source}`,
    `**Status:** ${row.status}`,
    `**Next action:** ${row.next_action}`,
    "",
    "## Fit",
    "",
    `- Fit score: ${formatScore(match?.fit_score ?? match?.score)}`,
    `- CV score: ${formatScore(match?.cv_score)}`,
    `- Location score: ${formatScore(match?.location_score)}`,
    `- Role track: ${match?.role_track || "-"}`,
    `- Best CV: ${match?.best_variant || "-"}`,
    "",
    "## Explanation",
    "",
    explanation.why_this_role || "No match explanation recorded.",
    "",
    explanation.why_this_cv || "",
    "",
    "## Gaps and Risks",
    "",
    `**Missing keywords:** ${missing}`,
    "",
    `**Risk flags:** ${riskFlags}`,
    "",
    "Applications stay manual. Use generated packs and apply on the employer or job-board site.",
  ].join("\n");
}

export function formatScore(score: number | undefined): string {
  return typeof score === "number" && Number.isFinite(score) ? score.toFixed(1) : "-";
}
