#!/usr/bin/env python3
"""Create a per-job review folder: match JSON, keyword gaps, paths to PDFs, checklist."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from career_job_search.core.paths import project_path
from career_job_search.cvs.matching import (
    PROFILES_PATH,
    derive_job_id,
    load_profiles,
    match_job_to_variants,
    parse_job_file,
)
from career_job_search.opportunities.packs import write_pack_files

PACKS_PARENT = project_path("packs")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build job-search/packs/<id>/ review folder."
    )
    parser.add_argument(
        "job_file",
        type=Path,
        help="Path to inbox job .txt",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=PROFILES_PATH,
        help="variant_profiles.yaml path",
    )
    parser.add_argument(
        "--job-id",
        type=str,
        default=None,
        help="Override folder name under packs/ (default: JOB_ID meta or derived)",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        help="Force CV variant slug (for example: business-process-operations, operations-management, luxury-retail)",
    )
    parser.add_argument(
        "--packs-dir",
        type=Path,
        default=PACKS_PARENT,
        help="Destination parent directory (default: job-search/packs)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing pack directory.",
    )
    args = parser.parse_args()

    if not args.job_file.is_file():
        print(f"Not a file: {args.job_file}", file=sys.stderr)
        sys.exit(1)

    variants = load_profiles(args.profiles)
    valid_slugs = set(variants.keys())

    raw = args.job_file.read_text(encoding="utf-8")
    parsed = parse_job_file(raw, job_file_path=str(args.job_file.resolve()))
    result = match_job_to_variants(parsed, variants)

    if args.variant:
        if args.variant not in valid_slugs:
            print(
                f"Unknown slug {args.variant!r}. Allowed: {sorted(valid_slugs)}",
                file=sys.stderr,
            )
            sys.exit(1)
        chosen = args.variant
        result["recommendation"]["variant_slug"] = chosen
        result["recommendation"]["confidence"] = "manual_override"
    else:
        chosen = result["recommendation"]["variant_slug"]

    job_id = args.job_id or derive_job_id(parsed)
    pack_dir = args.packs_dir / job_id

    try:
        pack_files = write_pack_files(
            result, job_id, pack_dir, variants, overwrite=args.force
        )
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(f"Wrote pack: {pack_dir.resolve()}")
    print(f"  Recommended variant: {chosen} ({result['recommendation']['confidence']})")
    print("  Open README.txt inside the pack for paths and checklist.")
    print(
        f"  Pack files: {pack_files['readme']}, {pack_files['match_json']}, {pack_files['keyword_gaps']}"
    )


if __name__ == "__main__":
    main()
