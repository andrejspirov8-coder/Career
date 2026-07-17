import { describe, expect, it } from "vitest";
import { calculateAnalytics, getUpcomingDeadlines } from "../utils/analytics";

describe("analytics helpers", () => {
  it("calculates pipeline, variant, and source metrics", () => {
    const analytics = calculateAnalytics([
      {
        date_iso: "2026-05-01",
        company: "A",
        title: "Manager",
        variant_slug: "luxury-retail",
        source: "linkedin",
        outcome: "applied",
        notes: "",
      },
      {
        date_iso: "2026-05-02",
        company: "B",
        title: "Director",
        variant_slug: "luxury-retail",
        source: "cvbank",
        outcome: "interview",
        notes: "",
      },
      {
        date_iso: "2026-05-03",
        company: "C",
        title: "Ops",
        variant_slug: "operations-management",
        source: "cvbank",
        outcome: "rejected",
        notes: "",
      },
    ]);

    expect(analytics.pipeline.applied).toBe(3);
    expect(analytics.pipeline.interview).toBe(1);
    expect(analytics.pipeline.interviewRate).toBeCloseTo(33.333, 3);
    expect(analytics.variantPerformance.find((row) => row.variantSlug === "luxury-retail")).toMatchObject({
      applied: 2,
      interviews: 1,
      rate: 50,
    });
    expect(analytics.sourcePerformance.find((row) => row.source === "cvbank")).toMatchObject({
      total: 2,
      interviews: 1,
      rate: 50,
    });
  });

  it("returns deadlines within the next seven days grouped by day distance", () => {
    const deadlines = getUpcomingDeadlines(
      [
        {
          date_iso: "2026-05-19",
          company: "Michael Kors",
          title: "ASM",
          variant_slug: "luxury-retail",
          source: "cvbank",
          outcome: "applied",
          deadline_date: "2026-05-22",
          notes: "",
        },
        {
          date_iso: "2026-05-19",
          company: "Too Far",
          title: "Role",
          variant_slug: "it-business",
          source: "linkedin",
          outcome: "applied",
          deadline_date: "2026-06-10",
          notes: "",
        },
      ],
      new Date("2026-05-19T12:00:00Z"),
    );

    expect(deadlines).toEqual([
      expect.objectContaining({
        company: "Michael Kors",
        title: "ASM",
        daysUntil: 3,
      }),
    ]);
  });
});
