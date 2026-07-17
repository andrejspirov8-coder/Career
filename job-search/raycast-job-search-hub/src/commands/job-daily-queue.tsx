import { Action, ActionPanel, Detail, Icon, launchCommand, LaunchType, showToast, Toast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { errorMessage } from "../utils/errors";
import {
  parseOpportunityCommandSummary,
  summarizeOpportunityOverview,
  type OpportunityCommandPayload,
  type OpportunityOverview,
} from "../utils/opportunities";
import { runOpportunityDailyQueue, runOpportunityReport } from "../utils/python-runner";

export default function JobDailyQueueCommand() {
  const [logs, setLogs] = useState<string[]>(["Preparing daily queue..."]);
  const [isRunning, setIsRunning] = useState(true);
  const [queueResult, setQueueResult] = useState<OpportunityCommandPayload | undefined>();
  const [overview, setOverview] = useState<OpportunityOverview | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [runKey, setRunKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setIsRunning(true);
      setQueueResult(undefined);
      setOverview(undefined);
      setError(undefined);
      setLogs(["Refreshing and scoring opportunities..."]);
      try {
        const queue = await runOpportunityDailyQueue();
        if (cancelled) return;
        setQueueResult(queue);
        setLogs((current) => [...current, parseOpportunityCommandSummary(queue), "Loading review queues..."]);

        const nextOverview = await runOpportunityReport();
        if (cancelled) return;
        setOverview(nextOverview);
        const summary = summarizeOpportunityOverview(nextOverview);
        setLogs((current) => [...current, summary.subtitle, "Applications stay manual."]);
        await showToast({ style: Toast.Style.Success, title: "Daily queue ready", message: summary.subtitle });
      } catch (caughtError) {
        if (cancelled) return;
        setError(errorMessage(caughtError));
        await showToast({
          style: Toast.Style.Failure,
          title: "Daily queue failed",
          message: "Check the command output.",
        });
      } finally {
        if (!cancelled) setIsRunning(false);
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [runKey]);

  const markdown = useMemo(() => {
    const summary = overview ? summarizeOpportunityOverview(overview) : undefined;
    return [
      "# Job: Daily Queue",
      "",
      `**Status:** ${error ? "Failed" : isRunning ? "Processing..." : "Ready for review"}`,
      "",
      summary
        ? `**Queue:** ${summary.subtitle}`
        : "Refreshes opportunities, scores them, then opens a manual review queue.",
      "",
      "## Steps",
      "",
      `- Refresh and score: ${queueResult ? parseOpportunityCommandSummary(queueResult) : isRunning ? "running" : "not run"}`,
      "- Review: use the action below to inspect Apply Today, Needs CV Tailoring, Missing Outcome, and Follow Up.",
      "",
      "## Output",
      "",
      "```text",
      ...logs,
      "```",
      error ? `\n## Error\n\n${error}` : "",
    ].join("\n");
  }, [error, isRunning, logs, overview, queueResult]);

  return (
    <Detail
      isLoading={isRunning}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action
            title="Review Opportunities"
            icon={Icon.Eye}
            onAction={() => launchCommand({ name: "job-review-opportunities", type: LaunchType.UserInitiated })}
          />
          <Action title="Run Again" icon={Icon.ArrowClockwise} onAction={() => setRunKey((key) => key + 1)} />
        </ActionPanel>
      }
    />
  );
}
