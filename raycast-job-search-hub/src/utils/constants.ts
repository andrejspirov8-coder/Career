import { join } from "node:path";
import { jobSources, outcomes, variantSlugs } from "../types";

export const JOB_ROOT = "/Users/andrejspirov/Career/job-search";
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
  "notes",
] as const;

export const sourceOptions = jobSources.map((source) => ({ title: source, value: source }));
export const variantOptions = variantSlugs.map((variant) => ({ title: variant, value: variant }));
export const outcomeOptions = outcomes.map((outcome) => ({ title: outcome, value: outcome }));
