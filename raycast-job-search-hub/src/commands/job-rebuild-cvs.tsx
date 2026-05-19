import { Action, ActionPanel, Detail, Icon, open, showToast, Toast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { OUTPUT_DIR } from "../utils/constants";
import { errorMessage } from "../utils/errors";
import { runRebuildCvs } from "../utils/python-runner";

export default function JobRebuildCvsCommand() {
  const [logs, setLogs] = useState<string[]>(["Preparing CV rebuild..."]);
  const [isRunning, setIsRunning] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [runKey, setRunKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setIsRunning(true);
      setError(undefined);
      setLogs(["Running cv/build_cv_pdf.py --all..."]);

      try {
        const output = await runRebuildCvs((text) => {
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

        if (!output.trim()) {
          setLogs((current) => [...current, "CV rebuild finished with no output."]);
        }

        await showToast({
          style: Toast.Style.Success,
          title: "CV rebuild complete",
          message: "PDFs and Canva text files were regenerated.",
        });
      } catch (caughtError) {
        if (cancelled) {
          return;
        }
        setError(errorMessage(caughtError));
        await showToast({
          style: Toast.Style.Failure,
          title: "CV rebuild failed",
          message: "Check the output below.",
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
    const status = isRunning ? "Processing..." : error ? "Failed" : "Finished";
    return [
      "# Job: Rebuild CVs",
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
  }, [error, isRunning, logs]);

  return (
    <Detail
      isLoading={isRunning}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action title="Run Again" icon={Icon.ArrowClockwise} onAction={() => setRunKey((key) => key + 1)} />
          <Action title="Open Output Folder" icon={Icon.Folder} onAction={() => open(OUTPUT_DIR)} />
        </ActionPanel>
      }
    />
  );
}
