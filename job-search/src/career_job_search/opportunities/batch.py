#!/usr/bin/env python3
"""
Batch automation: scan inbox/jobs/*.job.txt, match each to CV variants,
and generate application packs. Creates a summary report of all matches.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from career_job_search.cvs.matching import (
    JOB_ROOT,
    PROFILES_PATH,
    derive_job_id,
    load_profiles,
    match_job_to_variants,
    parse_job_file,
)
from career_job_search.opportunities.packs import write_pack_files

INBOX_JOBS = JOB_ROOT / "inbox" / "jobs"
PACKS_DIR = JOB_ROOT / "packs"


def scan_jobs(pattern: str = "*.job.txt") -> list[Path]:
    """Scan inbox/jobs for job files."""
    if not INBOX_JOBS.exists():
        return []
    return sorted(INBOX_JOBS.glob(pattern))


def process_single_job(
    job_file: Path,
    variants: dict[str, Any],
    dry_run: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Process one job file: parse, match, generate pack."""
    try:
        raw = job_file.read_text(encoding="utf-8")
        parsed = parse_job_file(raw, job_file_path=str(job_file.resolve()))
        result = match_job_to_variants(parsed, variants)
        result["job_root"] = str(JOB_ROOT.resolve())

        pack_id = derive_job_id(parsed)
        pack_dir = PACKS_DIR / pack_id

        pack_files: dict[str, str] = {}
        if not dry_run:
            pack_files = write_pack_files(
                result, pack_id, pack_dir, variants, overwrite=overwrite
            )

        recommendation = result["recommendation"]
        return {
            "status": "success",
            "job_file": str(job_file),
            "job_title": parsed.get("title", "(no title)"),
            "job_company": parsed.get("company", "(no company)"),
            "pack_id": pack_id,
            "pack_dir": str(pack_dir),
            "recommended_variant": recommendation["variant_slug"],
            "confidence": recommendation["confidence"],
            "match_score": recommendation["primary_score"],
            "runner_up": result["runner_up"]["variant_slug"],
            "all_variants": [
                {
                    "slug": v["slug"],
                    "score": v["primary_score"],
                    "hits": len(v["keyword_hits"]),
                }
                for v in result["variants_ranked"]
            ],
            "pack_files": pack_files,
        }
    except FileExistsError as exc:
        return {
            "status": "skipped",
            "job_file": str(job_file),
            "job_title": parsed.get("title", "(no title)"),
            "job_company": parsed.get("company", "(no company)"),
            "pack_id": pack_id,
            "pack_dir": str(pack_dir),
            "error": str(exc),
        }
    except Exception as e:
        return {
            "status": "error",
            "job_file": str(job_file),
            "error": str(e),
        }


def generate_summary_report(results: list[dict[str, Any]]) -> str:
    """Generate a human-readable summary report."""
    lines = [
        "# Batch Job Matching Summary Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    total = len(results)
    successes = [r for r in results if r["status"] == "success"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors = [r for r in results if r["status"] == "error"]

    lines.extend(
        [
            "## Overview",
            f"- Total jobs processed: {total}",
            f"- Successful matches: {len(successes)}",
            f"- Skipped existing packs: {len(skipped)}",
            f"- Errors: {len(errors)}",
            "",
        ]
    )

    if skipped:
        lines.extend(["## Skipped", ""])
        for item in skipped:
            lines.append(
                f"- {item.get('job_title', item['job_file'])} @ {item.get('job_company', '')}: {item['error']}"
            )
        lines.append("")

    if errors:
        lines.extend(["## Errors", ""])
        for err in errors:
            lines.append(f"### {err['job_file']}")
            lines.append(f"```\n{err['error']}\n```")
            lines.append("")

    if successes:
        lines.extend(["## Successful Matches", ""])

        for result in successes:
            lines.append(f"### {result['job_title']} @ {result['job_company']}")
            lines.append(f"- **Pack ID**: {result['pack_id']}")
            lines.append(
                f"- **Recommended**: `{result['recommended_variant']}` (confidence: {result['confidence']}, score: {result['match_score']})"
            )
            lines.append(f"- **Runner-up**: `{result['runner_up']}`")
            lines.append("- **All matches**:")
            for v in result["all_variants"]:
                lines.append(
                    f"  - {v['slug']}: score={v['score']}, keyword_hits={v['hits']}"
                )
            lines.append(f"- **Pack location**: `{result['pack_dir']}`")
            lines.append("")

    lines.extend(["## Variant Distribution", ""])

    variant_counts: dict[str, int] = {}
    for result in successes:
        variant = result["recommended_variant"]
        variant_counts[variant] = variant_counts.get(variant, 0) + 1

    lines.append("| Variant | Count |")
    lines.append("|---------|-------|")
    for variant, count in sorted(variant_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {variant} | {count} |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch match all job files in inbox/jobs to CV variants and generate packs."
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.job.txt",
        help="Glob pattern for job files (default: *.job.txt)",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=PROFILES_PATH,
        help="Override path to variant_profiles.yaml",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and match only, don't write pack files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing pack directories when generating packs.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write summary report to this path (defaults to summary_report_TIMESTAMP.md).",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=None,
        help="Also write raw JSON results to this path.",
    )
    args = parser.parse_args()

    # Load variants
    try:
        variants = load_profiles(args.profiles)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Scan jobs
    job_files = scan_jobs(args.pattern)
    if not job_files:
        print(
            f"No job files found matching '{args.pattern}' in {INBOX_JOBS}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found {len(job_files)} job file(s). Processing...", file=sys.stderr)

    # Process all jobs (with output buffering optimisation)
    results: list[dict[str, Any]] = []
    print_buffer: list[str] = []
    for job_file in job_files:
        result = process_single_job(
            job_file, variants, dry_run=args.dry_run, overwrite=args.force
        )
        results.append(result)
        status_mark = "✓" if result["status"] == "success" else "✗"
        print_buffer.append(f"  → {job_file.name}... {status_mark}")

    # Write all at once (single I/O call vs. N calls)
    if print_buffer:
        sys.stderr.write("\n".join(print_buffer) + "\n")

    # Generate summary report
    summary = generate_summary_report(results)

    # Write reports
    if args.report:
        report_path = args.report
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = JOB_ROOT / f"summary_report_{timestamp}.md"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(summary, encoding="utf-8")
    print(f"\n✓ Summary report: {report_path}", file=sys.stderr)

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"✓ JSON report: {args.json_report}", file=sys.stderr)

    # Print to stdout
    print(summary)

    sys.exit(0 if all(r["status"] == "success" for r in results) else 1)


if __name__ == "__main__":
    main()
