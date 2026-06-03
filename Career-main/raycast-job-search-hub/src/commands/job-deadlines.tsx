import { Action, ActionPanel, Icon, List, open, showToast, Toast } from "@raycast/api";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { useEffect, useMemo, useState } from "react";
import { format, parseISO } from "date-fns";
import { getUpcomingDeadlines } from "../utils/analytics";
import { APPLICATIONS_CSV_PATH } from "../utils/constants";
import { readApplications } from "../utils/csv-parser";
import { errorMessage } from "../utils/errors";
import type { DeadlineItem } from "../types";

export default function JobDeadlinesCommand() {
  const [deadlines, setDeadlines] = useState<DeadlineItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setIsLoading(true);
      try {
        const rows = await readApplications(APPLICATIONS_CSV_PATH);
        if (!cancelled) {
          setDeadlines(getUpcomingDeadlines(rows));
        }
      } catch (error) {
        await showToast({
          style: Toast.Style.Failure,
          title: "Could not load deadlines",
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

  const subtitle = useMemo(() => {
    if (deadlines.length === 0) {
      return "No upcoming deadlines in the next 7 days.";
    }
    return `${deadlines.length} upcoming deadline${deadlines.length === 1 ? "" : "s"}`;
  }, [deadlines.length]);

  return (
    <List isLoading={isLoading} navigationTitle="Job: Deadlines" searchBarPlaceholder="Search deadlines">
      <List.EmptyView title="No Upcoming Deadlines" description="Add a deadline when logging an application." />
      <List.Section title="Upcoming Deadlines" subtitle={subtitle}>
        {deadlines.map((deadline) => (
          <List.Item
            key={`${deadline.company}-${deadline.title}-${deadline.deadline_date}`}
            title={`${deadline.company} | ${deadline.title}`}
            subtitle={`Due ${deadlineLabel(deadline)}`}
            icon={Icon.Calendar}
            accessories={[{ text: deadline.variant_slug }, { text: deadline.outcome }]}
            actions={
              <ActionPanel>
                <Action
                  title="Add Calendar Reminder"
                  icon={Icon.Calendar}
                  onAction={() => addCalendarReminder(deadline)}
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

async function addCalendarReminder(deadline: DeadlineItem) {
  try {
    const directory = join(tmpdir(), "raycast-job-search-hub");
    await mkdir(directory, { recursive: true });
    const filePath = join(directory, `${slug(deadline.company)}-${slug(deadline.title)}.ics`);
    await writeFile(filePath, buildIcs(deadline), "utf8");
    await open(filePath);
  } catch (error) {
    await showToast({
      style: Toast.Style.Failure,
      title: "Could not create reminder",
      message: errorMessage(error),
    });
  }
}

function deadlineLabel(deadline: DeadlineItem): string {
  const date = deadline.deadline_date ? format(parseISO(deadline.deadline_date), "MMM d") : "soon";
  if (deadline.daysUntil === 0) {
    return `today (${date})`;
  }
  if (deadline.daysUntil === 1) {
    return `tomorrow (${date})`;
  }
  return `in ${deadline.daysUntil} days (${date})`;
}

function buildIcs(deadline: DeadlineItem): string {
  const date = (deadline.deadline_date ?? "").replaceAll("-", "");
  const uid = `${slug(deadline.company)}-${slug(deadline.title)}-${date}@raycast-job-search-hub`;
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Raycast Job Search Hub//EN",
    "BEGIN:VEVENT",
    `UID:${uid}`,
    `DTSTAMP:${format(new Date(), "yyyyMMdd'T'HHmmss'Z'")}`,
    `DTSTART;VALUE=DATE:${date}`,
    `SUMMARY:Apply deadline: ${escapeIcs(deadline.company)} | ${escapeIcs(deadline.title)}`,
    `DESCRIPTION:Variant: ${escapeIcs(deadline.variant_slug)}\\nApplied: ${escapeIcs(deadline.date_iso)}`,
    "END:VEVENT",
    "END:VCALENDAR",
    "",
  ].join("\r\n");
}

function slug(value: string): string {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "deadline"
  );
}

function escapeIcs(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/,/g, "\\,").replace(/;/g, "\\;").replace(/\n/g, "\\n");
}
