import { Action, ActionPanel, Detail, Icon, launchCommand, LaunchType, showToast, Toast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { countInboxJobs, runBatchMatch, type BatchMatchResult } from "../utils/python-runner";
import { errorMessage } from "../utils/errors";

export default function JobMatchCommand() {
  const [logs, setLogs] = useState<string[]>(["Preparing batch match..."]);
  const [isRunning, setIsRunning] = useState(true);
  const [result, setResult] = useState<BatchMatchResult | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [runKey, setRunKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setIsRunning(true);
      setResult(undefined);
      setError(undefined);
      setLogs(["Checking inbox/jobs..."]);

      try {
        const jobCount = await countInboxJobs();
        if (jobCount === 0) {
          setLogs(["No .job.txt files found in inbox/jobs.", "Create one with Job: New."]);
          setIsRunning(false);
          return;
        }

        setLogs([`Found ${jobCount} job file${jobCount === 1 ? "" : "s"}.`, "Running batch_match_and_pack.py..."]);
        const nextResult = await runBatchMatch((text) => {
          if (cancelled) {
            return;
          }
          setLogs((current) =>
            [
              ...current,
              ...text
                .split(/\r?\n/)
                .map((line) => line.trim())
                .filter(Boolean),
            ].slice(-60),
          );
        });

        if (cancelled) {
          return;
        }
        setResult(nextResult);
        await showToast({
          style: Toast.Style.Success,
          title: "Match complete",
          message: summaryText(nextResult),
        });
      } catch (caughtError) {
        if (cancelled) {
          return;
        }
        setError(errorMessage(caughtError));
        await showToast({
          style: Toast.Style.Failure,
          title: "Match failed",
          message: "Check the output and MATCH.json in the affected pack.",
        });
      } finally {
        if (!cancelled) {
          setIsRunning(false);
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [runKey]);

  const markdown = useMemo(() => {
    const status = result ? summaryText(result) : isRunning ? "Processing..." : error ? "Failed" : "Ready";
    return [
      `# Job: Match All`,
      "",
      `**Status:** ${status}`,
      "",
      "## Output",
      "",
      "```text",
      ...logs,
      "```",
      error ? `\n## Error\n\n${error}` : "",
    ].join("\n");
  }, [error, isRunning, logs, result]);

  return (
    <Detail
      isLoading={isRunning}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action title="Run Again" icon={Icon.ArrowClockwise} onAction={() => setRunKey((key) => key + 1)} />
          <Action
            title="Review Packs"
            icon={Icon.Eye}
            shortcut={{ modifiers: ["cmd"], key: "r" }}
            onAction={() => launchCommand({ name: "job-review", type: LaunchType.UserInitiated })}
          />
        </ActionPanel>
      }
    />
  );
}

function summaryText(result: BatchMatchResult): string {
  const processed = result.processed ?? "?";
  const clear = result.clearWinners ?? "?";
  const ties = result.ties ?? "?";
  return `Processed ${processed} jobs. ${clear} clear winners, ${ties} ties.`;
}
