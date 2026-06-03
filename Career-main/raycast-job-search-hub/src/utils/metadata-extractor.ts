import { readdir, readFile } from "node:fs/promises";
import { basename, join } from "node:path";
import type { PackSort, PackSummary } from "../types";

type JsonObject = Record<string, unknown>;

export async function extractPackMetadata(packDir: string): Promise<PackSummary> {
  const matchPath = join(packDir, "MATCH.json");
  const match = asObject(JSON.parse(await readFile(matchPath, "utf8")));
  const job = asObject(match.job);
  const recommendation = asObject(match.recommendation);
  const runnerUp = asObject(match.runner_up);
  const pack = asObject(match.pack);
  const id = basename(packDir);

  return {
    id,
    dir: packDir,
    matchPath,
    gapsPath: join(packDir, "KEYWORD_GAPS.md"),
    company: asString(job.company, "Unknown company"),
    title: asString(job.title, "Unknown title"),
    source: asString(job.source, "linkedin"),
    variantSlug: asString(recommendation.variant_slug, asString(pack.recommended_variant_slug, "unknown")),
    score: asNumber(recommendation.primary_score, 0),
    confidence: asString(recommendation.confidence, "unknown"),
    runnerUpVariantSlug: optionalString(runnerUp.variant_slug),
    runnerUpScore: optionalNumber(runnerUp.primary_score),
    pdfPath: optionalString(pack.pdf_visual_path),
    createdDate: parsePackDate(id),
  };
}

export async function scanPacks(packsDir: string): Promise<PackSummary[]> {
  const entries = await readdir(packsDir, { withFileTypes: true }).catch((error: unknown) => {
    if (isMissingDirectory(error)) {
      return [];
    }
    throw error;
  });

  const summaries: PackSummary[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const packDir = join(packsDir, entry.name);
    try {
      summaries.push(await extractPackMetadata(packDir));
    } catch {
      continue;
    }
  }
  return summaries;
}

export function filterPacks(packs: PackSummary[], variant: string): PackSummary[] {
  if (variant === "all") {
    return packs;
  }
  return packs.filter((pack) => pack.variantSlug === variant);
}

export function sortPacks(packs: PackSummary[], sort: PackSort): PackSummary[] {
  return [...packs].sort((left, right) => {
    if (sort === "company") {
      return left.company.localeCompare(right.company);
    }
    if (sort === "date") {
      return (right.createdDate ?? "").localeCompare(left.createdDate ?? "") || right.id.localeCompare(left.id);
    }
    if (sort === "confidence") {
      return confidenceRank(right.confidence) - confidenceRank(left.confidence) || right.score - left.score;
    }
    return right.score - left.score;
  });
}

export function summarizePacks(packs: PackSummary[]): string {
  const clear = packs.filter((pack) => pack.confidence === "clear_winner").length;
  const ties = packs.filter((pack) => pack.confidence === "tie").length;
  const distribution = packs.reduce<Record<string, number>>((counts, pack) => {
    counts[pack.variantSlug] = (counts[pack.variantSlug] ?? 0) + 1;
    return counts;
  }, {});
  const variantText = Object.entries(distribution)
    .map(([variant, count]) => `${variant}: ${count}`)
    .join(", ");

  return `Total: ${packs.length} | Clear: ${clear} | Ties: ${ties}${variantText ? ` | ${variantText}` : ""}`;
}

export function packDetailMarkdown(pack: PackSummary): string {
  return [
    `# ${pack.company} | ${pack.title}`,
    "",
    `Recommended variant: **${pack.variantSlug}**`,
    `Score: **${pack.score.toFixed(1)}**`,
    `Confidence: **${pack.confidence}**`,
    pack.runnerUpVariantSlug
      ? `Runner-up: **${pack.runnerUpVariantSlug}** (${(pack.runnerUpScore ?? 0).toFixed(1)})`
      : "Runner-up: not available",
    "",
    `Pack: \`${pack.id}\``,
  ].join("\n");
}

function confidenceRank(confidence: string): number {
  if (confidence === "clear_winner") {
    return 2;
  }
  if (confidence === "tie") {
    return 1;
  }
  return 0;
}

function parsePackDate(id: string): string | undefined {
  const match = /^(\d{4})(\d{2})(\d{2})/.exec(id);
  if (!match) {
    return undefined;
  }
  return `${match[1]}-${match[2]}-${match[3]}`;
}

function asObject(value: unknown): JsonObject {
  return typeof value === "object" && value !== null ? (value as JsonObject) : {};
}

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function isMissingDirectory(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error && (error as NodeJS.ErrnoException).code === "ENOENT";
}
