import { writeFile } from "node:fs/promises";
import { differenceInCalendarDays, format, parseISO } from "date-fns";
import type { AnalyticsSummary, ApplicationRow, DeadlineItem, PerformanceRow } from "../types";

const positiveOutcomes = new Set(["interview", "offer"]);

export function calculateAnalytics(rows: ApplicationRow[]): AnalyticsSummary {
  const pipeline = {
    applied: rows.length,
    screening: countOutcome(rows, "screening"),
    interview: countOutcome(rows, "interview"),
    offer: countOutcome(rows, "offer"),
    rejected: countOutcome(rows, "rejected"),
    withdrawn: countOutcome(rows, "withdrawn"),
    interviewRate: percentage(countPositive(rows), rows.length),
    rejectionRate: percentage(countOutcome(rows, "rejected"), rows.length),
  };

  return {
    pipeline,
    variantPerformance: performanceBy(rows, "variant_slug").map((row) => ({
      ...row,
      variantSlug: row.key,
      trend: calculateTrend(rows.filter((application) => application.variant_slug === row.key)),
      key: undefined,
    })),
    sourcePerformance: performanceBy(rows, "source").map((row) => ({
      source: row.key,
      total: row.total,
      interviews: row.interviews,
      rate: row.rate,
    })),
  };
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatBar(value: number, totalBlocks = 20): string {
  const filled = Math.round((Math.max(0, Math.min(100, value)) / 100) * totalBlocks);
  return `${"█".repeat(filled)}${"░".repeat(totalBlocks - filled)}`;
}

export function getUpcomingDeadlines(rows: ApplicationRow[], now = new Date()): DeadlineItem[] {
  return rows
    .flatMap((row) => {
      if (!row.deadline_date) {
        return [];
      }
      const daysUntil = differenceInCalendarDays(parseISO(row.deadline_date), now);
      if (daysUntil < 0 || daysUntil > 7) {
        return [];
      }
      return [{ ...row, daysUntil }];
    })
    .sort((left, right) => left.daysUntil - right.daysUntil || left.company.localeCompare(right.company));
}

export function analyticsMarkdown(summary: AnalyticsSummary, updatedAt = new Date()): string {
  const applied = summary.pipeline.applied || 1;
  const screeningRate = percentage(summary.pipeline.screening, applied);
  const offerRate = percentage(summary.pipeline.offer, applied);

  return [
    "# Application Pipeline",
    "",
    metricLine("Applied", summary.pipeline.applied, 100),
    metricLine("Screening", summary.pipeline.screening, screeningRate),
    metricLine("Interview", summary.pipeline.interview, summary.pipeline.interviewRate),
    metricLine("Offer", summary.pipeline.offer, offerRate),
    "",
    `Interview rate: ${summary.pipeline.interview}/${summary.pipeline.applied} (${formatPercent(summary.pipeline.interviewRate)})`,
    `Rejected: ${summary.pipeline.rejected} (${formatPercent(summary.pipeline.rejectionRate)})`,
    `Withdrawn: ${summary.pipeline.withdrawn}`,
    "",
    "## Variant Performance",
    "",
    "| Variant | Applied | Interview | Rate | Trend |",
    "| --- | ---: | ---: | ---: | --- |",
    ...summary.variantPerformance.map(
      (row) =>
        `| ${row.variantSlug ?? ""} | ${row.applied ?? 0} | ${row.interviews} | ${formatPercent(row.rate)} | ${trendSymbol(row.trend)} |`,
    ),
    "",
    "## Source Performance",
    "",
    "| Source | Total | Interviews | Rate |",
    "| --- | ---: | ---: | ---: |",
    ...summary.sourcePerformance.map(
      (row) => `| ${row.source ?? ""} | ${row.total ?? 0} | ${row.interviews} | ${formatPercent(row.rate)} |`,
    ),
    "",
    `_Last updated: ${format(updatedAt, "yyyy-MM-dd HH:mm")}_`,
  ].join("\n");
}

export async function exportAnalyticsCsv(filePath: string, summary: AnalyticsSummary): Promise<void> {
  const lines = [
    "section,label,total,interviews,rate,trend",
    ...summary.variantPerformance.map(
      (row) =>
        `variant,${csvCell(row.variantSlug ?? "")},${row.applied ?? 0},${row.interviews},${row.rate.toFixed(1)},${row.trend ?? ""}`,
    ),
    ...summary.sourcePerformance.map(
      (row) => `source,${csvCell(row.source ?? "")},${row.total ?? 0},${row.interviews},${row.rate.toFixed(1)},`,
    ),
  ];
  await writeFile(filePath, `${lines.join("\n")}\n`, "utf8");
}

function performanceBy(rows: ApplicationRow[], field: "variant_slug" | "source") {
  const buckets = new Map<string, ApplicationRow[]>();
  for (const row of rows) {
    const key = row[field] || "unknown";
    buckets.set(key, [...(buckets.get(key) ?? []), row]);
  }

  return [...buckets.entries()]
    .map(([key, applications]) => ({
      key,
      total: applications.length,
      applied: applications.length,
      interviews: countPositive(applications),
      rate: percentage(countPositive(applications), applications.length),
    }))
    .sort((left, right) => right.rate - left.rate || right.total - left.total || left.key.localeCompare(right.key));
}

function calculateTrend(rows: ApplicationRow[]): PerformanceRow["trend"] {
  if (rows.length < 3) {
    return "unknown";
  }
  const sorted = [...rows].sort((left, right) => left.date_iso.localeCompare(right.date_iso));
  const split = Math.floor(sorted.length / 2);
  const older = sorted.slice(0, split);
  const newer = sorted.slice(split);
  const olderRate = percentage(countPositive(older), older.length);
  const newerRate = percentage(countPositive(newer), newer.length);
  if (newerRate > olderRate) {
    return "up";
  }
  if (newerRate < olderRate) {
    return "down";
  }
  return "stable";
}

function countOutcome(rows: ApplicationRow[], outcome: string): number {
  return rows.filter((row) => row.outcome === outcome).length;
}

function countPositive(rows: ApplicationRow[]): number {
  return rows.filter((row) => positiveOutcomes.has(row.outcome)).length;
}

function percentage(part: number, whole: number): number {
  return whole === 0 ? 0 : (part / whole) * 100;
}

function metricLine(label: string, count: number, rate: number): string {
  return `${label.padEnd(10)} ${String(count).padStart(4)}   ${formatBar(rate)} ${formatPercent(rate).padStart(6)}`;
}

function trendSymbol(trend: PerformanceRow["trend"]): string {
  if (trend === "up") {
    return "↑";
  }
  if (trend === "down") {
    return "↓";
  }
  if (trend === "stable") {
    return "↔";
  }
  return "?";
}

function csvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}
