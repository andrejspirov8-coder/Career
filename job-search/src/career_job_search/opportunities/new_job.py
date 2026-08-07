#!/usr/bin/env python3
"""
Interactive helper to create a new .job.txt file with proper naming and format.

Usage:
  cd tools
  python new_job.py

Prompts for:
  - Job title
  - Company name
  - URL
  - Source (linkedin, cvbank, cv_lt, startup_lt, recruiter, company_site, indeed, work_in_lt)

Creates: inbox/jobs/YYYYMMDD_company_title.job.txt
"""

from __future__ import annotations

import re
import sys
from datetime import datetime

from career_job_search.core.paths import PROJECT_ROOT as JOB_ROOT

INBOX = JOB_ROOT / "inbox" / "jobs"

VALID_SOURCES = {
    "linkedin",
    "cvbank",
    "cv_lt",
    "startup_lt",
    "recruiter",
    "company_site",
    "indeed",
    "work_in_lt",
}


def slugify(text: str) -> str:
    """Convert text to safe slug (lowercase, hyphens)."""
    text = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s\-]", "", text)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def main() -> None:
    print("=" * 60)
    print("Create new job posting file (.job.txt)")
    print("=" * 60)
    print()

    # Collect inputs
    try:
        title = input("Job title: ").strip()
        if not title:
            print("❌ Job title cannot be empty.", file=sys.stderr)
            sys.exit(1)

        company = input("Company name: ").strip()
        if not company:
            print("❌ Company name cannot be empty.", file=sys.stderr)
            sys.exit(1)

        url = input("URL: ").strip()
        if not url:
            print("⚠️  No URL provided (optional).", flush=True)
            url = ""

        print(f"\nValid sources: {', '.join(sorted(VALID_SOURCES))}")
        source = input("Source (or leave blank): ").strip().lower()
        if source and source not in VALID_SOURCES:
            print(
                f"⚠️  Warning: source '{source}' not in standard list, but proceeding.",
                flush=True,
            )

    except KeyboardInterrupt:
        print("\n❌ Cancelled.", file=sys.stderr)
        sys.exit(1)
    except EOFError:
        print("\n❌ EOF reached.", file=sys.stderr)
        sys.exit(1)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d")
    safe_title = slugify(title)[:30]  # First 4 words or ~30 chars
    safe_company = slugify(company)[:20]  # First 2 words or ~20 chars

    if not safe_title:
        safe_title = "role"
    if not safe_company:
        safe_company = "company"

    filename = f"{timestamp}_{safe_company}_{safe_title}.job.txt"
    filepath = INBOX / filename

    # Check for collisions
    if filepath.exists():
        print(f"\n❌ File already exists: {filepath}", file=sys.stderr)
        overwrite = input("Overwrite? (y/N): ").strip().lower()
        if overwrite != "y":
            print("Cancelled.", file=sys.stderr)
            sys.exit(1)

    # Create template
    template = f"""TITLE: {title}
COMPANY: {company}
URL: {url}
SOURCE: {source}
JOB_ID:
---
[Paste full job description here]
"""

    # Write file
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(template, encoding="utf-8")

    print(f"\n✓ Created: {filepath}")
    print("  Edit in your editor, then run:")
    print(f"    cd {JOB_ROOT / 'tools'}")
    print("    python batch_match_and_pack.py")


if __name__ == "__main__":
    main()
