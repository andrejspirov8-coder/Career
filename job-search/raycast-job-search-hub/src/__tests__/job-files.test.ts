import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { buildJobFileContent, buildJobId, createJobPostingFile } from "../utils/job-files";

const tempRoots: string[] = [];

async function makeRoot() {
  const root = await mkdtemp(join(tmpdir(), "job-hub-files-"));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("job file helpers", () => {
  it("generates a stable date, company, and title based job id", () => {
    expect(buildJobId("Michael Kors", "Assistant Store Manager", new Date("2026-05-19T09:00:00Z"))).toBe(
      "20260519_michael_kors_assistant_store_manager",
    );
  });

  it("renders the expected .job.txt template", () => {
    expect(
      buildJobFileContent({
        title: "Assistant Store Manager",
        company: "Michael Kors",
        url: "https://example.test/job",
        source: "linkedin",
        jobId: "20260519_michael_kors_assistant_store_manager",
      }),
    ).toBe(
      [
        "TITLE: Assistant Store Manager",
        "COMPANY: Michael Kors",
        "URL: https://example.test/job",
        "SOURCE: linkedin",
        "JOB_ID: 20260519_michael_kors_assistant_store_manager",
        "---",
        "[Paste full job description here]",
        "",
      ].join("\n"),
    );
  });

  it("creates the inbox directory and refuses to overwrite unless allowed", async () => {
    const root = await makeRoot();
    const first = await createJobPostingFile({
      jobRoot: root,
      title: "Director",
      company: "Zara Home",
      url: "",
      source: "cvbank",
      now: new Date("2026-05-19T09:00:00Z"),
    });

    await expect(
      createJobPostingFile({
        jobRoot: root,
        title: "Director",
        company: "Zara Home",
        url: "",
        source: "cvbank",
        jobId: first.jobId,
        now: new Date("2026-05-19T09:00:00Z"),
      }),
    ).rejects.toThrow("already exists");

    const content = await readFile(first.filePath, "utf8");
    expect(content).toContain("COMPANY: Zara Home");
  });
});
