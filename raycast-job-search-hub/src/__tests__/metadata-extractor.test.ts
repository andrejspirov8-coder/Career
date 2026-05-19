import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, describe, expect, it } from "vitest";
import { extractPackMetadata, filterPacks, scanPacks, sortPacks } from "../utils/metadata-extractor";

const tempRoots: string[] = [];

async function makeRoot() {
  const root = await mkdtemp(join(tmpdir(), "job-hub-packs-"));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function writePack(root: string, id: string, score: number, variant = "luxury-retail") {
  const packDir = join(root, id);
  await mkdir(packDir, { recursive: true });
  await writeFile(
    join(packDir, "MATCH.json"),
    JSON.stringify({
      job: {
        title: "Boutique Manager",
        company: id.includes("zara") ? "Zara Home" : "Example Maison",
        source: "linkedin",
      },
      recommendation: {
        variant_slug: variant,
        confidence: score > 15 ? "clear_winner" : "tie",
        primary_score: score,
      },
      runner_up: {
        variant_slug: "operations-management",
        primary_score: 11,
      },
      pack: {
        pdf_visual_path: `/tmp/${id}.pdf`,
      },
    }),
  );
  return packDir;
}

describe("pack metadata helpers", () => {
  it("extracts recommendation, runner-up, paths, and job fields from MATCH.json", async () => {
    const root = await makeRoot();
    const packDir = await writePack(root, "20260519-example-maison", 25);

    expect(await extractPackMetadata(packDir)).toMatchObject({
      id: "20260519-example-maison",
      company: "Example Maison",
      title: "Boutique Manager",
      variantSlug: "luxury-retail",
      score: 25,
      confidence: "clear_winner",
      runnerUpVariantSlug: "operations-management",
      runnerUpScore: 11,
      pdfPath: "/tmp/20260519-example-maison.pdf",
    });
  });

  it("scans only pack directories with MATCH.json and sorts by score", async () => {
    const root = await makeRoot();
    await writePack(root, "20260519-zara-home", 17, "operations-management");
    await writePack(root, "20260520-example-maison", 25, "luxury-retail");

    const packs = await scanPacks(root);
    expect(sortPacks(packs, "score").map((pack) => pack.id)).toEqual(["20260520-example-maison", "20260519-zara-home"]);
    expect(filterPacks(packs, "operations-management")).toHaveLength(1);
  });
});
