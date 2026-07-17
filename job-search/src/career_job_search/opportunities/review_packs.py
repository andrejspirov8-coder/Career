#!/usr/bin/env python3
"""
Quick dashboard to review all generated application packs.

Usage:
  cd tools
  python review_packs.py           # Show all packs
  python review_packs.py --sort score  # Sort by match score (default)
  python review_packs.py --sort date   # Sort by date (newest first)
  python review_packs.py --filter luxury-retail  # Filter by variant

Shows a tabular summary of:
  - Pack ID (date + company + role)
  - Job title
  - Recommended variant
  - Match confidence
  - Score
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT

PACKS_DIR = JOB_ROOT / "packs"


def load_pack(pack_dir: Path) -> dict[str, Any] | None:
    """Load MATCH.json from pack; return None if malformed."""
    match_file = pack_dir / "MATCH.json"
    if not match_file.exists():
        return None
    try:
        return json.loads(match_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_pack_info(pack_dir: Path, match_data: dict[str, Any]) -> dict[str, Any]:
    """Extract human-readable info from pack and MATCH.json."""
    job = match_data.get("job", {})
    rec = match_data.get("recommendation", {})

    return {
        "pack_id": pack_dir.name,
        "date": pack_dir.name[:8],  # YYYYMMDD
        "title": job.get("title", "(untitled)")[:30],
        "company": job.get("company", "(unknown)")[:20],
        "variant": rec.get("variant_slug", "unknown"),
        "confidence": rec.get("confidence", "?"),
        "score": rec.get("primary_score", 0.0),
        "runner_up": match_data.get("runner_up", {}).get("variant_slug", "?"),
    }


def format_confidence(conf: str) -> str:
    """Format confidence with emoji."""
    if conf == "clear_winner":
        return "✓ clear"
    elif conf == "tie_review":
        return "⚠ tie"
    else:
        return f"? {conf}"


def print_header() -> None:
    """Print table header."""
    print(
        f"{'Pack ID':<45} | "
        f"{'Title':<28} | "
        f"{'Variant':<20} | "
        f"{'Confidence':<10} | "
        f"{'Score':>6}"
    )
    print("-" * 130)


def print_row(info: dict[str, Any]) -> None:
    """Print one pack info row."""
    conf_str = format_confidence(info["confidence"])
    print(
        f"{info['pack_id']:<45} | "
        f"{info['title']:<28} | "
        f"{info['variant']:<20} | "
        f"{conf_str:<10} | "
        f"{info['score']:>6.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Review all generated application packs.")
    parser.add_argument(
        "--sort",
        type=str,
        choices=["score", "date", "variant"],
        default="score",
        help="Sort by: score (desc), date (newest), or variant (alphabetical)",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter packs by variant slug (e.g., 'luxury-retail')",
    )
    args = parser.parse_args()

    # Scan packs
    if not PACKS_DIR.exists():
        print(f"❌ Packs directory not found: {PACKS_DIR}", file=sys.stderr)
        sys.exit(1)

    packs: list[tuple[Path, dict[str, Any]]] = []
    for pack_dir in sorted(PACKS_DIR.glob("20*")):
        if not pack_dir.is_dir():
            continue
        match_data = load_pack(pack_dir)
        if match_data:
            packs.append((pack_dir, match_data))

    if not packs:
        print("ℹ️  No packs found.", file=sys.stderr)
        sys.exit(0)

    # Extract info
    infos = [extract_pack_info(pack_dir, match_data) for pack_dir, match_data in packs]

    # Filter
    if args.filter:
        infos = [info for info in infos if info["variant"] == args.filter]
        if not infos:
            print(f"ℹ️  No packs match variant filter: {args.filter}", file=sys.stderr)
            sys.exit(0)

    # Sort
    if args.sort == "score":
        infos.sort(key=lambda x: x["score"], reverse=True)
    elif args.sort == "date":
        infos.sort(key=lambda x: x["date"], reverse=True)
    elif args.sort == "variant":
        infos.sort(key=lambda x: x["variant"])

    # Print
    print()
    print_header()
    for info in infos:
        print_row(info)
    print()
    print(f"Total packs: {len(infos)}")

    # Summary by variant
    variant_counts: dict[str, int] = {}
    for info in infos:
        v = info["variant"]
        variant_counts[v] = variant_counts.get(v, 0) + 1

    if len(variant_counts) > 1:
        print("\nVariant distribution:")
        for v, cnt in sorted(variant_counts.items(), key=lambda x: -x[1]):
            print(f"  - {v:<20} {cnt:>2} packs")


if __name__ == "__main__":
    main()
