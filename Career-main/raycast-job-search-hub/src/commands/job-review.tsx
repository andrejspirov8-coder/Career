import { Action, ActionPanel, Color, Icon, launchCommand, LaunchType, List, showToast, Toast } from "@raycast/api";
import { useEffect, useMemo, useState } from "react";
import { PACKS_DIR, variantOptions } from "../utils/constants";
import { errorMessage } from "../utils/errors";
import { filterPacks, packDetailMarkdown, scanPacks, sortPacks, summarizePacks } from "../utils/metadata-extractor";
import type { PackSort, PackSummary } from "../types";

type VariantFilter = "all" | string;

export default function JobReviewCommand() {
  const [packs, setPacks] = useState<PackSummary[]>([]);
  const [variant, setVariant] = useState<VariantFilter>("all");
  const [sort, setSort] = useState<PackSort>("score");
  const [isLoading, setIsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      try {
        const nextPacks = await scanPacks(PACKS_DIR);
        if (!cancelled) {
          setPacks(nextPacks);
        }
      } catch (error) {
        await showToast({
          style: Toast.Style.Failure,
          title: "Could not load packs",
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

  const visiblePacks = useMemo(() => sortPacks(filterPacks(packs, variant), sort), [packs, sort, variant]);

  return (
    <List
      isLoading={isLoading}
      isShowingDetail
      navigationTitle="Job: Review"
      searchBarPlaceholder="Search packs"
      searchBarAccessory={
        <List.Dropdown tooltip="Filter packs" value={variant} onChange={setVariant}>
          <List.Dropdown.Item title="All Variants" value="all" />
          {variantOptions.map((option) => (
            <List.Dropdown.Item key={option.value} title={option.title} value={option.value} />
          ))}
        </List.Dropdown>
      }
    >
      <List.EmptyView
        title="No packs found"
        description="Run Job: Match All after creating at least one .job.txt file."
        actions={
          <ActionPanel>
            <Action
              title="Run Match All"
              icon={Icon.Play}
              onAction={() => launchCommand({ name: "job-match", type: LaunchType.UserInitiated })}
            />
          </ActionPanel>
        }
      />
      <List.Section title="Application Packs" subtitle={summarizePacks(visiblePacks)}>
        {visiblePacks.map((pack) => (
          <List.Item
            key={pack.id}
            title={`${pack.company} | ${pack.title}`}
            subtitle={pack.id}
            icon={{ source: confidenceIcon(pack.confidence), tintColor: confidenceColor(pack.confidence) }}
            accessories={[
              { text: pack.variantSlug },
              { text: pack.score.toFixed(1) },
              { text: pack.confidence === "clear_winner" ? "Clear" : "Tie" },
            ]}
            detail={<List.Item.Detail markdown={packDetailMarkdown(pack)} />}
            actions={
              <ActionPanel>
                <ActionPanel.Section>
                  <Action.Open title="View Gaps" icon={Icon.Text} target={pack.gapsPath} />
                  {pack.pdfPath ? <Action.Open title="Open PDF" icon={Icon.Document} target={pack.pdfPath} /> : null}
                  <Action
                    title="Log Application"
                    icon={Icon.Pencil}
                    onAction={() =>
                      launchCommand({
                        name: "job-log",
                        type: LaunchType.UserInitiated,
                        context: { packDir: pack.dir },
                      })
                    }
                  />
                </ActionPanel.Section>
                <ActionPanel.Section title="View">
                  <Action title="Refresh" icon={Icon.ArrowClockwise} onAction={() => setRefreshKey((key) => key + 1)} />
                  <Action title="Sort by Score" onAction={() => setSort("score")} />
                  <Action title="Sort by Date" onAction={() => setSort("date")} />
                  <Action title="Sort by Company" onAction={() => setSort("company")} />
                  <Action title="Sort by Confidence" onAction={() => setSort("confidence")} />
                </ActionPanel.Section>
              </ActionPanel>
            }
          />
        ))}
      </List.Section>
    </List>
  );
}

function confidenceIcon(confidence: string) {
  return confidence === "clear_winner" ? Icon.CheckCircle : Icon.Clock;
}

function confidenceColor(confidence: string) {
  return confidence === "clear_winner" ? Color.Green : Color.Yellow;
}
