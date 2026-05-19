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
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
JOB_ROOT = TOOLS_DIR.parent
APPLICATIONS_CSV = JOB_ROOT / "pipeline" / "applications.csv"


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
        
        stats[variant]["total"] += 1
        stats[variant][outcome] += 1
    
    # Compute rates
    results = {}
    for variant, outcome_counts in sorted(stats.items()):
        total = outcome_counts["total"]
        applied = outcome_counts.get("applied", 0) + outcome_counts.get("screening", 0) + \
                  outcome_counts.get("interview", 0) + outcome_counts.get("offer", 0) + \
                  outcome_counts.get("rejected", 0)
        if applied == 0:
            applied = total
        
        interviews = outcome_counts.get("interview", 0) + outcome_counts.get("offer", 0)
        interview_rate = interviews / applied if applied > 0 else 0.0
        
        results[variant] = {
            "total": total,
            "applied": applied,
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
        
        stats[source]["total"] += 1
        stats[source][outcome] += 1
    
    # Compute rates
    results = {}
    for source, outcome_counts in sorted(stats.items()):
        total = outcome_counts["total"]
        applied = outcome_counts.get("applied", 0) + outcome_counts.get("screening", 0) + \
                  outcome_counts.get("interview", 0) + outcome_counts.get("offer", 0) + \
                  outcome_counts.get("rejected", 0)
        if applied == 0:
            applied = total
        
        interviews = outcome_counts.get("interview", 0) + outcome_counts.get("offer", 0)
        interview_rate = interviews / applied if applied > 0 else 0.0
        
        results[source] = {
            "total": total,
            "applied": applied,
            "interviews": interviews,
            "interview_rate": interview_rate,
        }
    
    return results


def print_variant_table(results: dict[str, dict[str, Any]]) -> None:
    """Print variant analysis as table."""
    print("\n" + "=" * 100)
    print("CV VARIANT PERFORMANCE")
    print("=" * 100)
    print(f"{'Variant':<25} {'Applied':>7} {'Rejected':>9} {'Screening':>10} {'Interview':>10} {'Offer':>7} {'Rate':>7}")
    print("-" * 100)
    
    for variant in sorted(results.keys()):
        data = results[variant]
        rate_str = f"{data['interview_rate']:.1%}"
        print(
            f"{variant:<25} "
            f"{data['applied']:>7} "
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
    print(f"{'Source':<25} {'Total':>7} {'Interviews':>12} {'Rate':>7}")
    print("-" * 80)
    
    for source in sorted(results.keys()):
        data = results[source]
        rate_str = f"{data['interview_rate']:.1%}"
        print(
            f"{source:<25} "
            f"{data['total']:>7} "
            f"{data['interviews']:>12} "
            f"{rate_str:>7}"
        )
    print()


def print_csv_variant(results: dict[str, dict[str, Any]]) -> None:
    """Print variant analysis as CSV."""
    print("variant,applied,rejected,screening,interview,offer,interview_rate")
    for variant in sorted(results.keys()):
        data = results[variant]
        print(
            f"{variant},{data['applied']},{data['rejected']},{data['screening']},"
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
    args = parser.parse_args()

    # Load data
    rows = load_applications()
    if not rows:
        print(f"ℹ️  No applications found in {APPLICATIONS_CSV}", file=sys.stderr)
        print("\nAdd rows to applications.csv:", file=sys.stderr)
        print("  date_iso,company,title,variant_slug,source,outcome,deadline_date,notes", file=sys.stderr)
        sys.exit(0)

    # Analyse
    if args.by == "source":
        results = analyse_by_source(rows)
        if args.csv:
            print("source,total,interviews,interview_rate")
            for source in sorted(results.keys()):
                data = results[source]
                print(f"{source},{data['total']},{data['interviews']},{data['interview_rate']:.4f}")
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
