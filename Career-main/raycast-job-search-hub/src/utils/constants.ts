import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { jobSources, outcomes, variantSlugs } from "../types";

export const JOB_ROOT_ENV_VAR = "CAREER_JOB_SEARCH_ROOT";

interface ResolveJobRootOptions {
  env?: NodeJS.ProcessEnv;
  candidates?: string[];
  exists?: (path: string) => boolean;
}

export function defaultJobRootCandidates(home = homedir()): string[] {
  return [
    join(home, "Career", "Career-main", "job-search"),
    join(home, "Downloads", "Career-main", "job-search"),
    join(home, "Career", "job-search"),
  ];
}

export function resolveJobRoot({
  env = process.env,
  candidates = defaultJobRootCandidates(),
  exists = existsSync,
}: ResolveJobRootOptions = {}): string {
  const configured = env[JOB_ROOT_ENV_VAR]?.trim();
  if (configured) {
    return configured;
  }
  return candidates.find((candidate) => exists(candidate)) ?? candidates[0];
}

export const JOB_ROOT = resolveJobRoot();
export const INBOX_JOBS_DIR = join(JOB_ROOT, "inbox", "jobs");
export const PACKS_DIR = join(JOB_ROOT, "packs");
export const OUTPUT_DIR = join(JOB_ROOT, "output");
export const APPLICATIONS_CSV_PATH = join(JOB_ROOT, "pipeline", "applications.csv");
export const BATCH_MATCH_SCRIPT = join(JOB_ROOT, "tools", "batch_match_and_pack.py");
export const CV_BUILD_SCRIPT = join(JOB_ROOT, "cv", "build_cv_pdf.py");

export const applicationColumns = [
  "date_iso",
  "company",
  "title",
  "variant_slug",
  "source",
  "outcome",
  "deadline_date",
  "match_score",
  "match_confidence",
  "salary_range",
  "tailored_cv",
  "response_date",
  "notes",
] as const;

export const sourceOptions = jobSources.map((source) => ({ title: source, value: source }));
export const variantOptions = variantSlugs.map((variant) => ({ title: variant, value: variant }));
export const outcomeOptions = outcomes.map((outcome) => ({ title: outcome, value: outcome }));
