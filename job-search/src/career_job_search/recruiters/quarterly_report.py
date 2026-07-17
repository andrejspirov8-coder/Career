#!/usr/bin/env python3
"""
Recruiter Quarterly Performance Report Generator

Reads pipeline/recruiters.csv and generates monthly/quarterly analytics.
"""

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT

RECRUITERS_CSV = JOB_ROOT / "pipeline" / "recruiters.csv"
OUTPUT_REPORT = JOB_ROOT / "pipeline" / "recruiter_quarterly_report.md"


def tier_from_score(score: float) -> str:
    """Infer tier from score if not already in row."""
    if score >= 15:
        return "tier_1"
    elif score >= 12:
        return "tier_2"
    elif score >= 8:
        return "tier_3"
    else:
        return "tier_rest"


def parse_response_status(status_str: str) -> bool:
    """Check if status indicates a response (accepted, messaged, viewed, etc.)."""
    return bool(status_str and any(s in status_str.lower() for s in [
        "accepted",
        "messaged",
        "replied",
        "response",
        "viewed",
        "profile_viewed",
    ]))


def analyze_recruiter_data(since: datetime | None = None) -> dict[str, Any]:
    """Read recruiters.csv and compute quarterly analytics."""

    if not RECRUITERS_CSV.exists():
        # Return empty report if no CSV yet
        return {
            "total_sent": 0,
            "total_responses": 0,
            "overall_response_rate": 0.0,
            "tier_stats": {},
            "company_stats": {},
            "variant_stats": {},
            "persona_stats": {},
            "score_distribution": {},
            "confidence_stats": {},
            "rows_analyzed": 0,
        }

    rows = []
    with RECRUITERS_CSV.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    # Filter by date if provided
    if since:
        filtered = []
        for row in rows:
            date_str = row.get("date_iso") or row.get("date") or ""
            if date_str:
                try:
                    row_date = datetime.fromisoformat(date_str.split("T")[0])
                    if row_date >= since:
                        filtered.append(row)
                except ValueError:
                    filtered.append(row)
            else:
                filtered.append(row)
        rows = filtered

    # Aggregate data
    by_tier = defaultdict(list)
    by_company = defaultdict(list)

    total_sent = 0
    total_responses = 0

    for row in rows:
        status = (row.get("status") or "").lower()
        if "would_" not in status:
            total_sent += 1

        score = float(row.get("primary_score") or 0)
        tier = row.get("tier") or tier_from_score(score)
        company = (row.get("company") or "Unknown").strip()
        response_status = (row.get("response_status") or "").lower()

        is_response = parse_response_status(response_status)
        if is_response:
            total_responses += 1

        by_tier[tier].append({"is_response": is_response, "score": score})
        by_company[company].append({"is_response": is_response})

    # Compute response rates by tier
    tier_stats = {}
    for tier in sorted(by_tier.keys()):
        profiles = by_tier[tier]
        responses = sum(1 for p in profiles if p["is_response"])
        rate = 100 * responses / len(profiles) if profiles else 0
        avg_score = sum(p["score"] for p in profiles) / len(profiles) if profiles else 0
        tier_stats[tier] = {
            "sent": len(profiles),
            "responses": responses,
            "response_rate": rate,
            "avg_score": avg_score,
        }

    # Compute company performance
    company_stats = {}
    for company in sorted(by_company.keys(), key=lambda c: len(by_company[c]), reverse=True)[:10]:
        profiles = by_company[company]
        responses = sum(1 for p in profiles if p["is_response"])
        rate = 100 * responses / len(profiles) if profiles else 0
        company_stats[company] = {
            "sent": len(profiles),
            "responses": responses,
            "response_rate": rate,
        }

    return {
        "total_sent": total_sent,
        "total_responses": total_responses,
        "overall_response_rate": 100 * total_responses / total_sent if total_sent else 0,
        "tier_stats": tier_stats,
        "company_stats": company_stats,
        "rows_analyzed": len(rows),
    }


def generate_report(data: dict[str, Any]) -> str:
    """Format analytics data as Markdown report."""

    report = f"""# Recruiter Quarterly Performance Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

**Rows analyzed:** {data["rows_analyzed"]}

---

## Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Total contacts sent** | {data["total_sent"]} | 20–30 | {'✓' if 20 <= data["total_sent"] <= 30 else '⚠️'} |
| **Total responses** | {data["total_responses"]} | {data["total_sent"] // 4 if data["total_sent"] else 0}+ | {'✓' if data["overall_response_rate"] >= 25 else '❌'} |
| **Overall response rate** | {data["overall_response_rate"]:.1f}% | ≥25% | {'✓' if data["overall_response_rate"] >= 25 else '❌'} |

---

## Response Rate by Tier

"""

    report += "| Tier | Sent | Responses | Rate | Target | Status |\n"
    report += "|------|------|-----------|------|--------|--------|\n"

    targets = {"tier_1": 50, "tier_2": 30, "tier_3": 15}
    for tier in ["tier_1", "tier_2", "tier_3", "tier_rest"]:
        if tier in data["tier_stats"]:
            stats = data["tier_stats"][tier]
            target = targets.get(tier, 0)
            status = "✓" if stats["response_rate"] >= target else "❌" if target > 0 else "–"
            report += f"| **{tier}** | {stats['sent']} | {stats['responses']} | {stats['response_rate']:.0f}% | ≥{target}% | {status} |\n"

    report += "\n---\n\n"

    # Top companies
    if data["company_stats"]:
        report += "## Top Performing Companies\n\n"
        report += "| Company | Sent | Responses | Rate |\n"
        report += "|---------|------|-----------|------|\n"
        for company, stats in list(data["company_stats"].items())[:10]:
            report += f"| {company} | {stats['sent']} | {stats['responses']} | {stats['response_rate']:.0f}% |\n"
        report += "\n---\n\n"

    # Recommendations
    report += "## Recommendations\n\n"
    if data["overall_response_rate"] < 25:
        report += "⚠️ **Response rate below 25% target.** Recommendations:\n\n"
        if data["tier_stats"].get("tier_3", {}).get("response_rate", 0) == 0:
            report += "1. **Raise Tier 3 threshold:** min_primary_score 12 → 13\n"
        if data["tier_stats"].get("tier_2", {}).get("sent", 0) > 0:
            report += "2. **Require clear_winner for Tier 2:** Set require_clear_winner: true\n"
    else:
        report += "✓ **Response rate on target.** Continue current strategy.\n"

    report += "\n---\n\n**End Report**\n"

    return report


def main():
    parser = argparse.ArgumentParser(description="Generate recruiter quarterly report")
    parser.add_argument("--output", type=Path, default=None, help="Write to file (default: stdout)")
    parser.add_argument("--since", type=str, default=None, help="Only analyze records since YYYY-MM-DD")
    args = parser.parse_args()

    # Parse --since if provided
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError:
            print(f"Invalid date format: {args.since}. Use YYYY-MM-DD")
            return 1

    # Generate report
    data = analyze_recruiter_data(since=since)
    report = generate_report(data)

    # Output
    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    exit(main())
