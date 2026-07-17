import { spawn } from "node:child_process";
import { readdir } from "node:fs/promises";
import { join } from "node:path";
import { BATCH_MATCH_SCRIPT, CV_BUILD_SCRIPT, JOB_ROOT } from "./constants";
import type { OpportunityCommandPayload, OpportunityOverview } from "./opportunities";

export const DEFAULT_PROCESS_TIMEOUT_MS = 5 * 60 * 1000;

export interface ProcessResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export interface BatchMatchResult {
  output: string;
  processed?: number;
  clearWinners?: number;
  ties?: number;
}

export interface CvVariantOption {
  title: string;
  value: string;
}

export function uvPythonInvocation(script: string, args: string[] = []) {
  return {
    command: "uv",
    args: ["run", "python", script, ...args],
  };
}

export async function countInboxJobs(jobRoot = JOB_ROOT): Promise<number> {
  const jobsDir = join(jobRoot, "inbox", "jobs");
  const entries = await readdir(jobsDir).catch((error: unknown) => {
    if (error instanceof Error && "code" in error && (error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw error;
  });
  return entries.filter((entry) => entry.endsWith(".job.txt")).length;
}

export async function runRebuildCvs(onOutput?: (text: string) => void): Promise<string> {
  const result = await runUvPython(CV_BUILD_SCRIPT, ["--all"], JOB_ROOT, onOutput);
  return combinedOutput(result);
}

export async function runBatchMatch(onOutput?: (text: string) => void): Promise<BatchMatchResult> {
  const result = await runUvPython(BATCH_MATCH_SCRIPT, [], join(JOB_ROOT, "tools"), onOutput);
  return {
    output: combinedOutput(result),
    ...parseBatchSummary(result.stdout),
  };
}

export async function runOpportunityDiscover(onOutput?: (text: string) => void): Promise<OpportunityCommandPayload> {
  const result = await runUvPython("tools/opportunity_orchestrate.py", ["discover"], JOB_ROOT, onOutput, [0, 2]);
  return parseJsonPayload(result.stdout);
}

export async function runOpportunityMatch(onOutput?: (text: string) => void): Promise<OpportunityCommandPayload> {
  const result = await runUvPython("tools/opportunity_orchestrate.py", ["match"], JOB_ROOT, onOutput);
  return parseJsonPayload(result.stdout);
}

export async function runOpportunityDailyQueue(onOutput?: (text: string) => void): Promise<OpportunityCommandPayload> {
  const result = await runUvPython("tools/opportunity_orchestrate.py", ["daily-queue"], JOB_ROOT, onOutput, [0, 2]);
  return parseJsonPayload(result.stdout);
}

export async function runOpportunityReport(onOutput?: (text: string) => void): Promise<OpportunityOverview> {
  const result = await runUvPython("tools/opportunity_orchestrate.py", ["report"], JOB_ROOT, onOutput);
  const payload = parseJsonPayload(result.stdout);
  if (!payload.ok) {
    throw new Error(payload.error || "Opportunity report failed.");
  }
  return payload.data as OpportunityOverview;
}

export async function loadCvVariantOptions(jobRoot = JOB_ROOT): Promise<CvVariantOption[]> {
  const result = await runUvPython("tools/cv_catalogue.py", [], jobRoot);
  return parseCvCataloguePayload(result.stdout);
}

export function parseCvCataloguePayload(stdout: string): CvVariantOption[] {
  const payload = JSON.parse(stdout.trim() || "{}") as {
    schema?: string;
    ok?: boolean;
    data?: { schema?: string; variants?: Array<{ slug?: unknown; name?: unknown }> };
    error?: string;
  };
  if (payload.schema !== "career_python_helper_v1" || !payload.ok || payload.data?.schema !== "cv_catalogue_v1") {
    throw new Error(payload.error || "CV catalogue returned an invalid contract.");
  }
  const variants = payload.data.variants;
  if (!Array.isArray(variants) || variants.length === 0) {
    throw new Error("CV catalogue contains no variants.");
  }
  return variants.map((variant) => {
    if (typeof variant.slug !== "string" || !variant.slug || typeof variant.name !== "string" || !variant.name) {
      throw new Error("CV catalogue contains an invalid variant.");
    }
    return { title: variant.name, value: variant.slug };
  });
}

function runUvPython(
  script: string,
  args: string[],
  cwd: string,
  onOutput?: (text: string) => void,
  acceptedExitCodes: number[] = [0],
): Promise<ProcessResult> {
  const invocation = uvPythonInvocation(script, args);
  return runProcess(invocation.command, invocation.args, cwd, onOutput, acceptedExitCodes);
}

export function runProcess(
  command: string,
  args: string[],
  cwd: string,
  onOutput?: (text: string) => void,
  acceptedExitCodes: number[] = [0],
  timeoutMs = DEFAULT_PROCESS_TIMEOUT_MS,
): Promise<ProcessResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let forceKillTimer: ReturnType<typeof setTimeout> | undefined;

    const timeoutTimer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      forceKillTimer = setTimeout(() => child.kill("SIGKILL"), 1_000);
    }, timeoutMs);

    const clearTimers = () => {
      clearTimeout(timeoutTimer);
      if (forceKillTimer) clearTimeout(forceKillTimer);
    };

    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      stdout += text;
      onOutput?.(text);
    });

    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      stderr += text;
      onOutput?.(text);
    });

    child.once("error", (error) => {
      clearTimers();
      reject(new Error(`Unable to start ${command}: ${error.message}`));
    });
    child.once("close", (code) => {
      clearTimers();
      const exitCode = code ?? 1;
      const result = { stdout, stderr, exitCode };
      if (timedOut) {
        reject(
          new Error(
            formatProcessFailure(
              `Command timed out after ${Math.ceil(timeoutMs / 1000)} second(s) and was cancelled`,
              command,
              args,
              result,
            ),
          ),
        );
        return;
      }
      if (!acceptedExitCodes.includes(exitCode)) {
        reject(new Error(formatProcessFailure(`Command exited with code ${exitCode}`, command, args, result)));
        return;
      }
      resolve(result);
    });
  });
}

export function parseJsonPayload(stdout: string): OpportunityCommandPayload {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error("Opportunity command returned no output.");
  }
  return JSON.parse(trimmed) as OpportunityCommandPayload;
}

export function parseBatchSummary(output: string): Omit<BatchMatchResult, "output"> {
  const processed = firstNumber(output, /processed\s+(\d+)/i) ?? firstNumber(output, /(\d+)\s+jobs?/i);
  const clearWinners = firstNumber(output, /(\d+)\s+clear/i);
  const ties = firstNumber(output, /(\d+)\s+ties?/i);
  return { processed, clearWinners, ties };
}

function combinedOutput(result: ProcessResult): string {
  return [result.stdout.trimEnd(), result.stderr.trimEnd()].filter(Boolean).join("\n");
}

function formatProcessFailure(summary: string, command: string, args: string[], result: ProcessResult): string {
  const details = [`${summary}: ${[command, ...args].join(" ")}`];
  if (result.stdout.trim()) details.push(`stdout:\n${result.stdout.trim()}`);
  if (result.stderr.trim()) details.push(`stderr:\n${result.stderr.trim()}`);
  return details.join("\n");
}

function firstNumber(text: string, pattern: RegExp): number | undefined {
  const match = pattern.exec(text);
  return match ? Number(match[1]) : undefined;
}
