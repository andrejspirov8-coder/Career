export const jobSources = [
  "linkedin",
  "cvbank",
  "cv_lt",
  "startup_lt",
  "recruiter",
  "company_site",
  "indeed",
  "work_in_lt",
] as const;

export const outcomes = ["applied", "rejected", "screening", "interview", "offer", "withdrawn"] as const;

export type JobSource = (typeof jobSources)[number];
export type VariantSlug = string;
export type ApplicationOutcome = (typeof outcomes)[number];

export interface ApplicationRow {
  date_iso: string;
  company: string;
  title: string;
  variant_slug: string;
  source: string;
  outcome: string;
  deadline_date?: string;
  match_score?: string;
  match_confidence?: string;
  salary_range?: string;
  tailored_cv?: string;
  response_date?: string;
  opportunity_id?: string;
  pack_dir?: string;
  application_url?: string;
  notes: string;
}

export interface JobPostingInput {
  title: string;
  company: string;
  url: string;
  source: string;
  jobId: string;
}

export interface CreateJobPostingInput {
  jobRoot: string;
  title: string;
  company: string;
  url?: string;
  source: string;
  jobId?: string;
  overwrite?: boolean;
  now?: Date;
}

export interface CreatedJobPosting {
  jobId: string;
  filePath: string;
  filename: string;
}

export type PackConfidence = "clear_winner" | "tie" | string;

export interface PackSummary {
  id: string;
  dir: string;
  matchPath: string;
  gapsPath: string;
  company: string;
  title: string;
  source: string;
  url?: string;
  variantSlug: string;
  score: number;
  confidence: PackConfidence;
  runnerUpVariantSlug?: string;
  runnerUpScore?: number;
  pdfPath?: string;
  createdDate?: string;
}

export type PackSort = "score" | "date" | "company" | "confidence";

export interface PipelineMetrics {
  applied: number;
  screening: number;
  interview: number;
  offer: number;
  rejected: number;
  withdrawn: number;
  interviewRate: number;
  rejectionRate: number;
}

export interface PerformanceRow {
  variantSlug?: string;
  source?: string;
  applied?: number;
  total?: number;
  interviews: number;
  rate: number;
  trend?: "up" | "down" | "stable" | "unknown";
}

export interface AnalyticsSummary {
  pipeline: PipelineMetrics;
  variantPerformance: PerformanceRow[];
  sourcePerformance: PerformanceRow[];
}

export interface DeadlineItem extends ApplicationRow {
  daysUntil: number;
}
