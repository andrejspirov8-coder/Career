import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { getPreferenceValues } from "@raycast/api";
import { jobSources, outcomes } from "../types";

export const JOB_ROOT_ENV_VAR = "CAREER_JOB_SEARCH_ROOT";

interface ResolveJobRootOptions {
  preferenceRoot?: string;
  env?: NodeJS.ProcessEnv;
  candidates?: string[];
  exists?: (path: string) => boolean;
}

export function defaultJobRootCandidates(home = homedir()): string[] {
  const normalizedHome = home.replace(/\/+$/, ""); // Remove trailing slashes
  return [join(normalizedHome, "Career", "job-search")];
}

export function resolveJobRoot({
  preferenceRoot,
  env = process.env,
  candidates = defaultJobRootCandidates(),
  exists = existsSync,
}: ResolveJobRootOptions = {}): string {
  const preferred = preferenceRoot?.trim();
  if (preferred) {
    return preferred;
  }
  const configured = env[JOB_ROOT_ENV_VAR]?.trim();
  if (configured) {
    return configured;
  }
  const found = candidates.find((candidate) => exists(candidate));
  if (found) {
    return found;
  }
  const fallback = candidates[0];
  if (!fallback) {
    throw new Error(
      "Could not resolve job-search root: no valid candidates found. " +
      "Set CAREER_JOB_SEARCH_ROOT environment variable or configure the " +
      "jobSearchRoot preference in Raycast."
    );
  }
  return fallback;
}

function configuredRaycastJobRoot(): string | undefined {
  if (process.env.NODE_ENV === "test") return undefined;
  try {
    return getPreferenceValues<{ jobSearchRoot?: string }>().jobSearchRoot;
  } catch {
    // The utilities also run under plain Node during tests and CI, where the
    // Raycast preferences bridge is unavailable.
    return undefined;
  }
}

export const JOB_ROOT = resolveJobRoot({ preferenceRoot: configuredRaycastJobRoot() });
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
  "opportunity_id",
  "pack_dir",
  "application_url",
  "notes",
] as const;

export const sourceOptions = jobSources.map((source) => ({ title: source, value: source }));
export const outcomeOptions = outcomes.map((outcome) => ({ title: outcome, value: outcome }));