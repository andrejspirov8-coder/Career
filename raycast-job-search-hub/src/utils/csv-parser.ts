import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { parse, stringify } from "csv/sync";
import { applicationColumns } from "./constants";
import type { ApplicationRow } from "../types";

type CsvCell = string | undefined;
type RawApplicationRow = Record<string, CsvCell>;

export async function readApplications(csvPath: string): Promise<ApplicationRow[]> {
  const content = await readFile(csvPath, "utf8").catch((error: unknown) => {
    if (isMissingFile(error)) {
      return "";
    }
    throw error;
  });

  if (!content.trim()) {
    return [];
  }

  const rows = parse(content, {
    columns: true,
    skip_empty_lines: true,
    bom: true,
  }) as RawApplicationRow[];

  return rows.map(normalizeApplicationRow);
}

export async function appendApplication(csvPath: string, row: ApplicationRow): Promise<void> {
  await ensureApplicationsCsv(csvPath);
  const normalized = normalizeApplicationRow(row);
  await appendFile(
    csvPath,
    stringify([normalized], {
      columns: applicationColumns as unknown as string[],
      header: false,
    }),
    "utf8",
  );
}

export async function ensureApplicationsCsv(csvPath: string): Promise<void> {
  await mkdir(dirname(csvPath), { recursive: true });

  const content = await readFile(csvPath, "utf8").catch((error: unknown) => {
    if (isMissingFile(error)) {
      return "";
    }
    throw error;
  });

  if (!content.trim()) {
    await writeFile(csvPath, `${applicationColumns.join(",")}\n`, "utf8");
    return;
  }

  const [headerLine] = content.split(/\r?\n/);
  const headers = headerLine.split(",");
  if (headers.includes("deadline_date")) {
    return;
  }

  const rows = await readApplications(csvPath);
  await writeFile(
    csvPath,
    stringify(rows, {
      columns: applicationColumns as unknown as string[],
      header: true,
    }),
    "utf8",
  );
}

export function normalizeApplicationRow(row: Partial<ApplicationRow>): ApplicationRow {
  return {
    date_iso: row.date_iso?.trim() ?? "",
    company: row.company?.trim() ?? "",
    title: row.title?.trim() ?? "",
    variant_slug: row.variant_slug?.trim() ?? "",
    source: row.source?.trim() ?? "",
    outcome: row.outcome?.trim() ?? "",
    deadline_date: row.deadline_date?.trim() ?? "",
    notes: row.notes?.trim() ?? "",
  };
}

function isMissingFile(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error && (error as NodeJS.ErrnoException).code === "ENOENT";
}
