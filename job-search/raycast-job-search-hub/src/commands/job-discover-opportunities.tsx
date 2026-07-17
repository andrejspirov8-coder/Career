import { Action, ActionPanel, Detail, Icon, launchCommand, LaunchType, showToast, Toast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { errorMessage } from "../utils/errors";
import { runOpportunityDiscover } from "../utils/python-runner";
import { parseOpportunityCommandSummary, type OpportunityCommandPayload } from "../utils/opportunities";

export default function JobDiscoverOpportunitiesCommand() {
  const [logs, setLogs] = useState<string[]>(["Preparing opportunity discovery..."]);
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
      setLogs(["Running opportunity discovery..."]);
      try {
        const payload = await runOpportunityDiscover();
        if (cancelled) return;
        setResult(payload);
        setLogs([parseOpportunityCommandSummary(payload), "Applications remain manual."]);
        await showToast({
          style: Toast.Style.Success,
          title: "Discovery complete",
          message: parseOpportunityCommandSummary(payload),
        });
      } catch (caughtError) {
        if (cancelled) return;
        setError(errorMessage(caughtError));
        await showToast({
          style: Toast.Style.Failure,
          title: "Discovery failed",
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
      "# Job: Discover Opportunities",
      "",
      `**Status:** ${status}`,
      "",
      "This command discovers and saves local opportunity leads. It does not apply to jobs.",
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
            title="Match Opportunities"
            icon={Icon.BullsEye}
            onAction={() => launchCommand({ name: "job-match-opportunities", type: LaunchType.UserInitiated })}
          />
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
