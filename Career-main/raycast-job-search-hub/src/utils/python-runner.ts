import { readdir } from "node:fs/promises";
import { spawn } from "node:child_process";
import { join } from "node:path";
import { BATCH_MATCH_SCRIPT, CV_BUILD_SCRIPT, JOB_ROOT } from "./constants";

export interface BatchMatchResult {
  output: string;
  processed?: number;
  clearWinners?: number;
  ties?: number;
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

export function runRebuildCvs(onOutput?: (text: string) => void): Promise<string> {
  return runPython("python3", [CV_BUILD_SCRIPT, "--all"], JOB_ROOT, onOutput);
}

export function runBatchMatch(onOutput?: (text: string) => void): Promise<BatchMatchResult> {
  return runPython("python3", [BATCH_MATCH_SCRIPT], join(JOB_ROOT, "tools"), onOutput).then((combined) => ({
    output: combined,
    ...parseBatchSummary(combined),
  }));
}

function runPython(command: string, args: string[], cwd: string, onOutput?: (text: string) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: process.env,
    });
    let output = "";
    let errorOutput = "";

    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      output += text;
      onOutput?.(text);
    });

    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      errorOutput += text;
      onOutput?.(text);
    });

    child.on("error", reject);
    child.on("close", (code) => {
      const combined = `${output}${errorOutput ? `\n${errorOutput}` : ""}`;
      if (code !== 0) {
        reject(new Error(combined.trim() || `${args[0]} exited with code ${code}`));
        return;
      }
      resolve(combined);
    });
  });
}

export function parseBatchSummary(output: string): Omit<BatchMatchResult, "output"> {
  const processed = firstNumber(output, /processed\s+(\d+)/i) ?? firstNumber(output, /(\d+)\s+jobs?/i);
  const clearWinners = firstNumber(output, /(\d+)\s+clear/i);
  const ties = firstNumber(output, /(\d+)\s+ties?/i);
  return { processed, clearWinners, ties };
}

function firstNumber(text: string, pattern: RegExp): number | undefined {
  const match = pattern.exec(text);
  return match ? Number(match[1]) : undefined;
}
