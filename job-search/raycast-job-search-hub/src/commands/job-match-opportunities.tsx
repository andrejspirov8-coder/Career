import { Action, ActionPanel, Detail, Icon, launchCommand, LaunchType, showToast, Toast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { errorMessage } from "../utils/errors";
import { parseOpportunityCommandSummary, type OpportunityCommandPayload } from "../utils/opportunities";
import { runOpportunityMatch } from "../utils/python-runner";

export default function JobMatchOpportunitiesCommand() {
  const [logs, setLogs] = useState<string[]>(["Preparing opportunity match..."]);
  const [isRunning, setIsRunning] = useState(true);
  const [result, setResult] = useState<OpportunityCommandPayload | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [runKey, setRunKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setIsRunning(true);
      setResult(undefined);
      setError(undefined);
      setLogs(["Scoring saved opportunities..."]);
      try {
        const payload = await runOpportunityMatch();
        if (cancelled) return;
        setResult(payload);
        setLogs([parseOpportunityCommandSummary(payload), "Review the queues before applying."]);
        await showToast({
          style: Toast.Style.Success,
          title: "Opportunity match complete",
          message: parseOpportunityCommandSummary(payload),
        });
      } catch (caughtError) {
        if (cancelled) return;
        setError(errorMessage(caughtError));
        await showToast({
          style: Toast.Style.Failure,
          title: "Opportunity match failed",
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
    const status = result
      ? parseOpportunityCommandSummary(result)
      : isRunning
        ? "Processing..."
        : error
          ? "Failed"
          : "Ready";
    return [
      "# Job: Match Opportunities",
      "",
      `**Status:** ${status}`,
      "",
      "This command scores saved opportunity leads against CV variants and review-first fit rules.",
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
            title="Review Opportunities"
            icon={Icon.Eye}
            onAction={() => launchCommand({ name: "job-review-opportunities", type: LaunchType.UserInitiated })}
          />
        </ActionPanel>
      }
    />
  );
}
