import { Action, ActionPanel, Color, Icon, launchCommand, LaunchType, List, showToast, Toast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { errorMessage } from "../utils/errors";
import {
  formatScore,
  opportunityDetailMarkdown,
  opportunityViewLabels,
  opportunityViewOrder,
  rowsForOpportunityView,
  summarizeOpportunityOverview,
  type OpportunityOverview,
} from "../utils/opportunities";
import { runOpportunityReport } from "../utils/python-runner";

type OpportunityView = (typeof opportunityViewOrder)[number];

export default function JobReviewOpportunitiesCommand() {
  const [overview, setOverview] = useState<OpportunityOverview | undefined>();
  const [view, setView] = useState<OpportunityView>("fresh_live_matches");
  const [isLoading, setIsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      try {
        const nextOverview = await runOpportunityReport();
        if (!cancelled) setOverview(nextOverview);
      } catch (error) {
        await showToast({
          style: Toast.Style.Failure,
          title: "Could not load opportunities",
          message: errorMessage(error),
        });
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const rows = useMemo(() => rowsForOpportunityView(overview, view), [overview, view]);
  const summary = overview ? summarizeOpportunityOverview(overview) : undefined;

  return (
    <List
      isLoading={isLoading}
      isShowingDetail
      navigationTitle="Job: Review Opportunities"
      searchBarPlaceholder="Search opportunities"
      searchBarAccessory={
        <List.Dropdown tooltip="Review queue" value={view} onChange={(value) => setView(value as OpportunityView)}>
          {opportunityViewOrder.map((option) => (
            <List.Dropdown.Item
              key={option}
              title={`${opportunityViewLabels[option]} (${rowsForOpportunityView(overview, option).length})`}
              value={option}
            />
          ))}
        </List.Dropdown>
      }
    >
      <List.EmptyView
        title={summary?.title || "No opportunities found"}
        description={summary?.subtitle || "Run Job: Discover Opportunities, then Job: Match Opportunities."}
        actions={
          <ActionPanel>
            <Action title="Refresh" icon={Icon.ArrowClockwise} onAction={() => setRefreshKey((key) => key + 1)} />
          </ActionPanel>
        }
      />
      <List.Section title={opportunityViewLabels[view]} subtitle={summary?.subtitle}>
        {rows.map((row) => (
          <List.Item
            key={`${view}-${row.opportunity_id}`}
            title={row.title || row.company || row.opportunity_id}
            subtitle={`${row.company || "-"}${row.location ? ` | ${row.location}` : ""}`}
            icon={{ source: iconForStatus(row.status), tintColor: colorForRisk(row.evidence?.risk_flags || []) }}
            accessories={[
              { text: row.match?.best_variant || "no CV" },
              { text: formatScore(row.match?.fit_score ?? row.match?.score) },
              { text: row.next_action },
            ]}
            detail={<List.Item.Detail markdown={opportunityDetailMarkdown(row)} />}
            actions={
              <ActionPanel>
                {row.source_url ? (
                  <Action.Open title="Open Source URL" icon={Icon.Link} target={row.source_url} />
                ) : null}
                <Action
                  title="Log Application"
                  icon={Icon.Pencil}
                  onAction={() =>
                    launchCommand({
                      name: "job-log",
                      type: LaunchType.UserInitiated,
                      context: {
                        opportunityId: row.opportunity_id,
                        company: row.company,
                        title: row.title,
                        variantSlug: row.match?.best_variant,
                        source: row.source,
                        matchScore: row.match?.fit_score ?? row.match?.score,
                        matchConfidence: row.match?.confidence,
                        packDir: row.pack?.pack_dir,
                        applicationUrl: row.source_url,
                        deadlineDate: row.deadline,
                        salaryRange: row.salary_text,
                      },
                    })
                  }
                />
                <Action title="Refresh" icon={Icon.ArrowClockwise} onAction={() => setRefreshKey((key) => key + 1)} />
              </ActionPanel>
            }
          />
        ))}
      </List.Section>
    </List>
  );
}

function iconForStatus(status: string) {
  if (status === "apply_ready") return Icon.CheckCircle;
  if (status === "review") return Icon.Eye;
  if (status === "expired") return Icon.Clock;
  return Icon.Document;
}

function colorForRisk(flags: string[]) {
  return flags.length ? Color.Yellow : Color.Green;
}
