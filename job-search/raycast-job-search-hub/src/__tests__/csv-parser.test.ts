import { mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { appendApplication, readApplications } from "../utils/csv-parser";

const tempRoots: string[] = [];

async function makeRoot() {
  const root = await mkdtemp(join(tmpdir(), "job-hub-csv-"));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("application CSV helpers", () => {
  it("creates the CSV with a header before appending the first row", async () => {
    const root = await makeRoot();
    const csvPath = join(root, "pipeline", "applications.csv");

    await appendApplication(csvPath, {
      date_iso: "2026-05-19",
      company: "Michael Kors, Lithuania",
      title: "ASM",
      variant_slug: "luxury-retail",
      source: "cvbank",
      outcome: "applied",
      notes: "Applied via email",
    });

    const content = await readFile(csvPath, "utf8");
    expect(content).toContain(
      "date_iso,company,title,variant_slug,source,outcome,deadline_date,match_score,match_confidence,salary_range,tailored_cv,response_date,opportunity_id,pack_dir,application_url,notes",
    );
    expect(content).toContain('"Michael Kors, Lithuania"');
  });

  it("reads both current and future deadline-aware CSV rows", async () => {
    const root = await makeRoot();
    const csvPath = join(root, "pipeline", "applications.csv");
    await appendApplication(csvPath, {
      date_iso: "2026-05-19",
      company: "Zara Home",
      title: "Director",
      variant_slug: "luxury-retail",
      source: "linkedin",
      outcome: "interview",
      deadline_date: "2026-05-26",
      notes: "Phone screen",
    });

    const rows = await readApplications(csvPath);
    expect(rows).toEqual([
      {
        date_iso: "2026-05-19",
        company: "Zara Home",
        title: "Director",
        variant_slug: "luxury-retail",
        source: "linkedin",
        outcome: "interview",
        deadline_date: "2026-05-26",
        match_score: "",
        match_confidence: "",
        salary_range: "",
        tailored_cv: "",
        response_date: "",
        opportunity_id: "",
        pack_dir: "",
        application_url: "",
        notes: "Phone screen",
      },
    ]);
  });

  it("normalizes opportunity tracking fields when logging applications", async () => {
    const root = await makeRoot();
    const csvPath = join(root, "pipeline", "applications.csv");
    await appendApplication(csvPath, {
      date_iso: "2026-06-30",
      company: "Vinted",
      title: "Operations Manager",
      variant_slug: "operations-management",
      source: "company_site",
      outcome: "applied",
      opportunity_id: " opp_123 ",
      pack_dir: " /tmp/pack ",
      application_url: " https://example.com/apply ",
      notes: "Applied manually",
    });

    const rows = await readApplications(csvPath);
    expect(rows[0]).toMatchObject({
      opportunity_id: "opp_123",
      pack_dir: "/tmp/pack",
      application_url: "https://example.com/apply",
    });
  });
});
