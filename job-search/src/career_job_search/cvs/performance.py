#!/usr/bin/env python3
"""
Analyse variant performance from applications.csv.

Usage:
  cd tools
  python variant_performance.py              # Show all variants
  python variant_performance.py --by source  # Break down by source channel
  python variant_performance.py --csv        # Output as CSV (for Excel/Sheets)

Tracks:
  - Applications submitted per variant
  - Interview callbacks
  - Conversion rates (interview / applied)
  - Outcome distribution
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from typing import Any

from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT

APPLICATIONS_CSV = JOB_ROOT / "pipeline" / "applications.csv"
SUBMITTED_OUTCOMES = {"applied", "screening", "interview", "offer", "rejected"}
POSITIVE_OUTCOMES = {"interview", "offer"}


def load_applications() -> list[dict[str, str]]:
    """Load and parse applications.csv."""
    if not APPLICATIONS_CSV.exists():
        return []

    rows: list[dict[str, str]] = []
    try:
        with open(APPLICATIONS_CSV, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                rows = list(reader)
    except Exception as e:
        print(f"⚠️  Error reading CSV: {e}", file=sys.stderr)

    return rows


def analyse_by_variant(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Analyse applications grouped by variant."""
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        variant = row.get("variant_slug", "unknown").strip()
        if not variant:
            continue
        outcome = row.get("outcome", "unknown").strip().lower()

        stats[variant]["total_rows"] += 1
        stats[variant][outcome] += 1

    results = {}
    for variant, outcome_counts in sorted(stats.items()):
        total_rows = outcome_counts["total_rows"]
        submitted = sum(outcome_counts.get(outcome, 0) for outcome in SUBMITTED_OUTCOMES)
        submitted = submitted or total_rows

        interviews = sum(outcome_counts.get(outcome, 0) for outcome in POSITIVE_OUTCOMES)
        interview_rate = interviews / submitted if submitted > 0 else 0.0

        results[variant] = {
            "total_rows": total_rows,
            "submitted": submitted,
            "rejected": outcome_counts.get("rejected", 0),
            "screening": outcome_counts.get("screening", 0),
            "interview": interviews,
            "offer": outcome_counts.get("offer", 0),
            "withdrawn": outcome_counts.get("withdrawn", 0),
            "interview_rate": interview_rate,
        }

    return results


def analyse_by_source(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Analyse applications grouped by source."""
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        source = row.get("source", "unknown").strip()
        if not source:
            continue
        outcome = row.get("outcome", "unknown").strip().lower()

        stats[source]["total_rows"] += 1
        stats[source][outcome] += 1

    results = {}
    for source, outcome_counts in sorted(stats.items()):
        total_rows = outcome_counts["total_rows"]
        submitted = sum(outcome_counts.get(outcome, 0) for outcome in SUBMITTED_OUTCOMES)
        submitted = submitted or total_rows

        interviews = sum(outcome_counts.get(outcome, 0) for outcome in POSITIVE_OUTCOMES)
        interview_rate = interviews / submitted if submitted > 0 else 0.0

        results[source] = {
            "total_rows": total_rows,
            "submitted": submitted,
            "interviews": interviews,
            "interview_rate": interview_rate,
        }

    return results


def analyse_roi(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Compare tailored vs untailored and high-score vs lower-score applications."""
    groups: dict[str, dict[str, dict[str, Any]]] = {
        "tailored_cv": defaultdict(lambda: {"submitted": 0, "interviews": 0, "response_days": []}),
        "match_score": defaultdict(lambda: {"submitted": 0, "interviews": 0, "response_days": []}),
    }

    for row in rows:
        outcome = (row.get("outcome") or "").strip().lower()
        if outcome not in SUBMITTED_OUTCOMES and outcome != "withdrawn":
            continue

        tailored = (row.get("tailored_cv") or "").strip().lower()
        tailored_key = "tailored_yes" if tailored in {"yes", "y", "true", "1"} else "tailored_no"
        score_key = _score_bucket(row.get("match_score") or "")

        for section, key in (("tailored_cv", tailored_key), ("match_score", score_key)):
            bucket = groups[section][key]
            bucket["submitted"] += 1
            if outcome in POSITIVE_OUTCOMES:
                bucket["interviews"] += 1
            response_days = _response_days(row)
            if response_days is not None:
                bucket["response_days"].append(response_days)

    out: dict[str, dict[str, dict[str, Any]]] = {"tailored_cv": {}, "match_score": {}}
    for section, buckets in groups.items():
        for key, counts in buckets.items():
            submitted = int(counts["submitted"])
            interviews = int(counts["interviews"])
            response_days = counts["response_days"]
            out[section][key] = {
                "submitted": submitted,
                "interviews": interviews,
                "interview_rate": interviews / submitted if submitted else 0.0,
                "avg_response_days": (sum(response_days) / len(response_days)) if response_days else None,
            }
    return out


def _score_bucket(raw_score: str) -> str:
    try:
        score = float(raw_score)
    except ValueError:
        return "no_score"
    if score >= 15.0:
        return "high_score_15_plus"
    return "lower_score_under_15"


def _response_days(row: dict[str, str]) -> int | None:
    submitted = _parse_date(row.get("date_iso") or "")
    response = _parse_date(row.get("response_date") or "")
    if submitted is None or response is None:
        return None
    delta = (response - submitted).days
    return delta if delta >= 0 else None


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def print_variant_table(results: dict[str, dict[str, Any]]) -> None:
    """Print variant analysis as table."""
    print("\n" + "=" * 100)
    print("CV VARIANT PERFORMANCE")
    print("=" * 100)
    print(
        f"{'Variant':<25} {'Submitted':>9} {'Rejected':>9} {'Screening':>10} {'Interview':>10} {'Offer':>7} {'Rate':>7}"
    )
    print("-" * 100)

    for variant in sorted(results.keys()):
        data = results[variant]
        rate_str = f"{data['interview_rate']:.1%}"
        print(
            f"{variant:<25} "
            f"{data['submitted']:>9} "
            f"{data['rejected']:>9} "
            f"{data['screening']:>10} "
            f"{data['interview']:>10} "
            f"{data['offer']:>7} "
            f"{rate_str:>7}"
        )
    print()


def print_source_table(results: dict[str, dict[str, Any]]) -> None:
    """Print source analysis as table."""
    print("\n" + "=" * 80)
    print("JOB SOURCE PERFORMANCE")
    print("=" * 80)
    print(f"{'Source':<25} {'Submitted':>9} {'Interviews':>12} {'Rate':>7}")
    print("-" * 80)

    for source in sorted(results.keys()):
        data = results[source]
        rate_str = f"{data['interview_rate']:.1%}"
        print(
            f"{source:<25} "
            f"{data['submitted']:>9} "
            f"{data['interviews']:>12} "
            f"{rate_str:>7}"
        )
    print()


def print_roi_tables(results: dict[str, dict[str, dict[str, Any]]]) -> None:
    print("\n" + "=" * 88)
    print("ROI CHECKS")
    print("=" * 88)
    for section, title in (
        ("tailored_cv", "TAILORED CV VS UNTAILORED"),
        ("match_score", "HIGH-SCORE VS LOWER-SCORE APPLICATIONS"),
    ):
        print(f"\n{title}")
        print(f"{'Group':<25} {'Submitted':>9} {'Interviews':>10} {'Rate':>7} {'Avg response':>13}")
        print("-" * 72)
        for key in sorted(results[section].keys()):
            data = results[section][key]
            avg = data["avg_response_days"]
            avg_str = f"{avg:.1f} days" if avg is not None else "-"
            print(
                f"{key:<25} "
                f"{data['submitted']:>9} "
                f"{data['interviews']:>10} "
                f"{data['interview_rate']:>6.1%} "
                f"{avg_str:>13}"
            )
    print()


def print_csv_variant(results: dict[str, dict[str, Any]]) -> None:
    """Print variant analysis as CSV."""
    print("variant,submitted,rejected,screening,interview,offer,interview_rate")
    for variant in sorted(results.keys()):
        data = results[variant]
        print(
            f"{variant},{data['submitted']},{data['rejected']},{data['screening']},"
            f"{data['interview']},{data['offer']},{data['interview_rate']:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse job application pipeline performance.")
    parser.add_argument(
        "--by",
        type=str,
        choices=["variant", "source"],
        default="variant",
        help="Analyse by variant (default) or by source",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output as CSV instead of human-readable table",
    )
    parser.add_argument(
        "--roi",
        action="store_true",
        help="Show tailoring, match-score, and response-time ROI checks",
    )
    args = parser.parse_args()

    # Load data
    rows = load_applications()
    if not rows:
        print(f"ℹ️  No applications found in {APPLICATIONS_CSV}", file=sys.stderr)
        print("\nAdd rows to applications.csv:", file=sys.stderr)
        print(
            "  date_iso,company,title,variant_slug,source,outcome,deadline_date,"
            "match_score,match_confidence,salary_range,tailored_cv,response_date,"
            "opportunity_id,pack_dir,application_url,notes",
            file=sys.stderr,
        )
        sys.exit(0)

    # Analyse
    if args.roi:
        print_roi_tables(analyse_roi(rows))
    elif args.by == "source":
        results = analyse_by_source(rows)
        if args.csv:
            print("source,submitted,interviews,interview_rate")
            for source in sorted(results.keys()):
                data = results[source]
                print(f"{source},{data['submitted']},{data['interviews']},{data['interview_rate']:.4f}")
        else:
            print_source_table(results)
    else:
        results = analyse_by_variant(rows)
        if args.csv:
            print_csv_variant(results)
        else:
            print_variant_table(results)


if __name__ == "__main__":
    main()
