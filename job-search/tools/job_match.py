#!/usr/bin/env python3
"""Score a pasted job posting against CV variant profiles (assistive only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from matching_lib import (
    JOB_ROOT,
    load_profiles,
    match_job_to_variants,
    matching_result_json,
    parse_job_file,
    PROFILES_PATH,
)


def human_summary(result: dict) -> str:
    lines = []
    job = result["job"]
    lines.append(f"Role: {job.get('title') or '(no TITLE)'} @ {job.get('company') or '(no COMPANY)'}")
    if job.get("url"):
        lines.append(f"URL: {job['url']}")
    rec = result["recommendation"]
    lines.append("")
    lines.append(
        f"Recommended variant: {rec['variant_slug']}  "
        f"(confidence: {rec['confidence']}, score={rec['primary_score']})"
    )
    ru = result["runner_up"]
    lines.append(
        f"Runner-up: {ru['variant_slug']}  (score={ru['primary_score']})"
    )
    lines.append("")
    lines.append("All variants (ranked):")
    for row in result["variants_ranked"]:
        lines.append(
            f"  - {row['slug']:<22} score={row['primary_score']:<8} tie={row['tie_break_score']}  "
            f"neg_hit={bool(row['negative_hits'])}"
        )
    if rec["confidence"] == "tie_review":
        lines.append("")
        lines.append("Note: Confidence is tie_review — open both top Markdown variants and pick manually.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Match one job inbox file to CV variants.")
    parser.add_argument(
        "job_file",
        type=Path,
        help="Path to inbox job .txt (see inbox/jobs/JOB_TEMPLATE.txt)",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=PROFILES_PATH,
        help="Override path to variant_profiles.yaml",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full JSON result to this path (directories created).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Print JSON only to stdout (no human summary).",
    )
    args = parser.parse_args()

    if not args.job_file.is_file():
        print(f"Not a file: {args.job_file}", file=sys.stderr)
        sys.exit(1)

    raw = args.job_file.read_text(encoding="utf-8")
    parsed = parse_job_file(raw, job_file_path=str(args.job_file.resolve()))
    variants = load_profiles(args.profiles)
    result = match_job_to_variants(parsed, variants)
    result["job_root"] = str(JOB_ROOT.resolve())

    if args.quiet:
        sys.stdout.write(matching_result_json(result))
    else:
        print(human_summary(result), end="")
        print("--- JSON ---")
        sys.stdout.write(matching_result_json(result))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(matching_result_json(result), encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {args.json_out.resolve()}", file=sys.stderr)


if __name__ == "__main__":
    main()
