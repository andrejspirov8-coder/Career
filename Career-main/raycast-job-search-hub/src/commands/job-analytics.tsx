import { Action, ActionPanel, Detail, Icon, showToast, Toast } from "@raycast/api";
import { join } from "node:path";
import { homedir } from "node:os";
import { useEffect, useMemo, useState } from "react";
import { analyticsMarkdown, calculateAnalytics, exportAnalyticsCsv } from "../utils/analytics";
import { APPLICATIONS_CSV_PATH } from "../utils/constants";
import { readApplications } from "../utils/csv-parser";
import { errorMessage } from "../utils/errors";
import type { AnalyticsSummary } from "../types";

export default function JobAnalyticsCommand() {
  const [summary, setSummary] = useState<AnalyticsSummary>(() => calculateAnalytics([]));
  const [updatedAt, setUpdatedAt] = useState(new Date());
  const [isLoading, setIsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      try {
        const rows = await readApplications(APPLICATIONS_CSV_PATH);
        if (!cancelled) {
          setSummary(calculateAnalytics(rows));
          setUpdatedAt(new Date());
        }
      } catch (error) {
        await showToast({
          style: Toast.Style.Failure,
          title: "Could not read analytics",
          message: errorMessage(error),
        });
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const markdown = useMemo(() => analyticsMarkdown(summary, updatedAt), [summary, updatedAt]);

  async function exportCsv() {
    const exportPath = join(homedir(), "Desktop", "job-search-analytics.csv");
    try {
      await exportAnalyticsCsv(exportPath, summary);
      await showToast({ style: Toast.Style.Success, title: "Exported analytics", message: exportPath });
    } catch (error) {
      await showToast({ style: Toast.Style.Failure, title: "Export failed", message: errorMessage(error) });
    }
  }

  return (
    <Detail
      isLoading={isLoading}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action title="Refresh" icon={Icon.ArrowClockwise} onAction={() => setRefreshKey((key) => key + 1)} />
          <Action title="Export as CSV" icon={Icon.Download} onAction={exportCsv} />
        </ActionPanel>
      }
    />
  );
}
