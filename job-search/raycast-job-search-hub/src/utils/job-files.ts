import { mkdir, writeFile } from "node:fs/promises";
import { basename, join } from "node:path";
import type { CreateJobPostingInput, CreatedJobPosting, JobPostingInput } from "../types";

export function slugifyPart(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_{2,}/g, "_");
}

export function buildJobId(company: string, title: string, now = new Date()): string {
  const date = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("");
  const companySlug = slugifyPart(company);
  const titleSlug = slugifyPart(title);
  return [date, companySlug, titleSlug].filter(Boolean).join("_");
}

export function buildJobFileContent(input: JobPostingInput): string {
  return [
    `TITLE: ${input.title}`,
    `COMPANY: ${input.company}`,
    `URL: ${input.url}`,
    `SOURCE: ${input.source}`,
    `JOB_ID: ${input.jobId}`,
    "---",
    "[Paste full job description here]",
    "",
  ].join("\n");
}

export async function createJobPostingFile(input: CreateJobPostingInput): Promise<CreatedJobPosting> {
  const title = input.title.trim();
  const company = input.company.trim();

  if (!title) {
    throw new Error("Job title is required.");
  }
  if (!company) {
    throw new Error("Company name is required.");
  }

  const jobId = input.jobId?.trim() || buildJobId(company, title, input.now);
  const jobsDir = join(input.jobRoot, "inbox", "jobs");
  const filePath = join(jobsDir, `${jobId}.job.txt`);
  const content = buildJobFileContent({
    title,
    company,
    url: input.url?.trim() ?? "",
    source: input.source,
    jobId,
  });

  await mkdir(jobsDir, { recursive: true });
  await writeFile(filePath, content, { encoding: "utf8", flag: input.overwrite ? "w" : "wx" }).catch(
    (error: unknown) => {
      if (isFileExistsError(error)) {
        throw new Error(`Job file already exists: ${filePath}`);
      }
      throw error;
    },
  );

  return {
    jobId,
    filePath,
    filename: basename(filePath),
  };
}

function isFileExistsError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error && (error as NodeJS.ErrnoException).code === "EEXIST";
}
