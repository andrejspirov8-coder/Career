#!/usr/bin/env python3
"""
Continuous job watcher: monitors inbox/jobs for new .job.txt files,
automatically matches them to CVs, and generates application packs.

Usage:
  python watch_and_match.py                    # Watch continuously
  python watch_and_match.py --once             # One scan, then exit
  python watch_and_match.py --interval 30      # Check every 30 seconds (default: 5)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from matching_lib import (
    JOB_ROOT,
    PROFILES_PATH,
    derive_job_id,
    load_profiles,
    match_job_to_variants,
    parse_job_file,
)
from pack_lib import write_pack_files

INBOX_JOBS = JOB_ROOT / "inbox" / "jobs"
PACKS_DIR = JOB_ROOT / "packs"
PROCESSED_LOG = JOB_ROOT / ".job_processing_log.json"


def load_processed_jobs() -> set[str]:
    """Load set of already-processed job file paths."""
    if not PROCESSED_LOG.exists():
        return set()
    try:
        data = json.loads(PROCESSED_LOG.read_text(encoding="utf-8"))
        return set(data.get("processed", []))
    except Exception:
        return set()


def save_processed_jobs(processed: set[str]) -> None:
    """Save set of processed job file paths."""
    data = {
        "processed": sorted(processed),
        "last_updated": datetime.now().isoformat(),
    }
    PROCESSED_LOG.write_text(json.dumps(data, indent=2), encoding="utf-8")


def process_job_file(
    job_file: Path,
    variants: dict[str, Any],
    verbose: bool = True,
    overwrite: bool = False,
) -> dict[str, Any] | None:
    """Process one job file and generate pack. Returns result dict or None on error."""
    try:
        if verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing: {job_file.name}", flush=True)

        raw = job_file.read_text(encoding="utf-8")
        parsed = parse_job_file(raw, job_file_path=str(job_file.resolve()))
        result = match_job_to_variants(parsed, variants)

        pack_id = derive_job_id(parsed)
        pack_dir = PACKS_DIR / pack_id

        try:
            pack_files = write_pack_files(result, pack_id, pack_dir, variants, overwrite=overwrite)
        except FileExistsError as exc:
            if verbose:
                print(f"  ↷ Skipping existing pack: {exc}", flush=True)
            return {
                "status": "skipped",
                "job_file": str(job_file),
                "pack_id": pack_id,
                "pack_dir": str(pack_dir),
                "title": parsed.get("title", "(untitled)"),
                "company": parsed.get("company", "(unknown)"),
                "variant": result["recommendation"]["variant_slug"],
                "confidence": result["recommendation"]["confidence"],
                "score": result["recommendation"]["primary_score"],
            }

        recommendation = result["recommendation"]
        if verbose:
            print(
                f"  ✓ {parsed.get('title', '(untitled)')} @ "
                f"{parsed.get('company', '(unknown)')}\n"
                f"    → {recommendation['variant_slug']} "
                f"(confidence: {recommendation['confidence']}, "
                f"score: {recommendation['primary_score']})\n"
                f"    → Pack: {pack_dir}",
                flush=True,
            )

        return {
            "status": "success",
            "job_file": str(job_file),
            "pack_id": pack_id,
            "pack_dir": str(pack_dir),
            "title": parsed.get("title", "(untitled)"),
            "company": parsed.get("company", "(unknown)"),
            "variant": recommendation["variant_slug"],
            "confidence": recommendation["confidence"],
            "score": recommendation["primary_score"],
            "pack_files": pack_files,
        }
    except Exception as e:
        if verbose:
            print(f"  ✗ Error: {e}", flush=True)
        return None


def scan_new_jobs(processed: set[str]) -> list[Path]:
    """Scan inbox/jobs for unprocessed .job.txt files."""
    if not INBOX_JOBS.exists():
        return []

    candidates = sorted(INBOX_JOBS.glob("*.job.txt"))
    new_jobs = [j for j in candidates if str(j.resolve()) not in processed]
    return new_jobs


def watch_and_process(
    interval_seconds: int = 5,
    once: bool = False,
    force: bool = False,
    variants: dict[str, Any] | None = None,
) -> None:
    """Watch inbox/jobs and process new files."""
    processed = load_processed_jobs()

    if variants is None:
        try:
            variants = load_profiles(PROFILES_PATH)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    iteration = 0
    while True:
        iteration += 1
        new_jobs = scan_new_jobs(processed)

        if iteration == 1 or new_jobs:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] Scanning for new jobs...", flush=True)

        if new_jobs:
            print(f"Found {len(new_jobs)} new job file(s):", flush=True)
            for job_file in new_jobs:
                result = process_job_file(job_file, variants, verbose=True, overwrite=force)
                if result:
                    processed.add(str(job_file.resolve()))

            save_processed_jobs(processed)
        else:
            if iteration == 1:
                print("No new jobs found.", flush=True)
            elif iteration % 12 == 0:  # Log every ~60 seconds (12 * 5s)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No new jobs.", flush=True)

        if once:
            break

        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch inbox/jobs for new job files and automatically match/pack."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Scan interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Scan once and exit (don't watch continuously).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing pack directories when generating packs.",
    )
    args = parser.parse_args()

    try:
        watch_and_process(interval_seconds=args.interval, once=args.once, force=args.force)
    except KeyboardInterrupt:
        print("\n[Interrupted by user]", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
