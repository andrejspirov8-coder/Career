import packageJson from "../../package.json";
import { describe, expect, it } from "vitest";
import {
  opportunityViewOrder,
  parseOpportunityCommandSummary,
  summarizeOpportunityOverview,
  type OpportunityCommandPayload,
} from "../utils/opportunities";

describe("opportunity Raycast helpers", () => {
  it("exposes daily opportunity commands in the Raycast manifest", () => {
    const commandNames = packageJson.commands.map((command) => command.name);

    expect(commandNames).toContain("job-discover-opportunities");
    expect(commandNames).toContain("job-review-opportunities");
    expect(commandNames).toContain("job-match-opportunities");
    expect(commandNames).toContain("job-daily-queue");
  });

  it("summarizes discover and match command JSON safely", () => {
    const discoverPayload: OpportunityCommandPayload = {
      ok: true,
      data: {
        count: 4,
        persisted: 4,
        dry_run: false,
      },
    };
    const matchPayload: OpportunityCommandPayload = {
      ok: true,
      data: {
        count: 3,
        persisted: 3,
      },
    };

    expect(parseOpportunityCommandSummary(discoverPayload)).toBe("Found 4 opportunities. Persisted 4.");
    expect(parseOpportunityCommandSummary(matchPayload)).toBe("Processed 3 opportunities. Persisted 3.");
  });

  it("summarizes the daily queue command without raw opportunity rows", () => {
    expect(
      parseOpportunityCommandSummary({
        ok: true,
        data: {
          discovered: 18,
          matched: 12,
          new_live_jobs: [],
          source_results: [
            {
              source: "greenhouse:broken",
              status: "failed",
              complete: false,
            },
          ],
          review_queue: {
            fresh_live_matches: 2,
            top_5_today: 5,
            apply_today: 3,
            needs_cv_tailoring: 4,
            missing_outcome: 1,
            follow_up: 2,
          },
        },
      }),
    ).toBe(
      "Discovered 18. Matched 12. Fresh 0, source failures 1, apply today 3, tailor CV 4, missing outcome 1, follow-up 2.",
    );
  });

  it("starts opportunity review with fresh live matches", () => {
    expect(opportunityViewOrder[0]).toBe("fresh_live_matches");
  });

  it("summarizes the review queue without offering auto apply", () => {
    expect(
      summarizeOpportunityOverview({
        counts: {
          total: 8,
          fresh_live_matches: 2,
          new_today: 2,
          updated_roles: 1,
          closing_soon: 1,
          top_5_today: 5,
          apply_today: 1,
          best_europe_matches: 3,
          apply_ready: 2,
          missing_outcome: 1,
          follow_up: 1,
          risk_flags: 1,
        },
        safe_actions: ["mark_review", "generate_pack", "mark_applied"],
      }),
    ).toEqual({
      title: "8 opportunities",
      subtitle: "2 fresh live, 1 apply today, 1 missing outcome, 1 follow-up",
      hasAutoApply: false,
    });
  });
});
